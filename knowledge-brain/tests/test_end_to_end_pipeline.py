"""End-to-End Pipeline & Integration Verification for Knowledge Brain (Step 1.5).

Verifies the complete integration across all Knowledge Brain components:
1. Crawled / parsed article HTML extraction (text, headings, image whitelist).
2. Sliding-window chunking preserving heading structure and screenshot metadata.
3. Vector embedding and persistent ChromaDB indexing.
4. Grounded semantic retrieval and Claude synthesis with strict citations.
5. Preservation of source URLs and screenshots through the entire pipeline.
6. Two-tier abstention and persistent human-expert escalation logging.
7. Closed-loop human feedback learning (auto-indexing resolved expert answers).
8. Failure resilience: empty retrieval, timeouts, API failures, malformed requests.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import anthropic
import pytest
from fastapi.testclient import TestClient

from src.api import app
from src.chunker import chunk_article
from src.config import Settings
from src.escalation_manager import EscalationManager
from src.html_parser import extract_article
from src.models import (
    ArticleRecord,
    ArticleStatus,
    EscalationStatus,
    ImageCitation,
    QueryRequest,
    QueryResponse,
    SourceCitation,
)
from src.rag_engine import RAGEngine
from src.vector_store import MockEmbeddingFunction, VectorStore

RAW_HTML_ARTICLE = """
<!DOCTYPE html>
<html>
<head><title>Guide: Setting Up Custom Membership Plans</title></head>
<body>
  <div class="breadcrumb">
    <a href="/support/home">Home</a> &gt;
    <a href="/support/solutions">Finance</a> &gt;
    <span>Membership Plans</span>
  </div>
  <article class="article-body">
    <h1>Setting Up Custom Membership Plans</h1>
    <p>Brilliant Directories allows website owners to create unlimited free or paid membership tiers.</p>
    
    <h2>Step 1: Access Membership Plans</h2>
    <p>From the admin dashboard, navigate to <strong>Finance &gt; Membership Plans</strong> to manage active tiers.</p>
    <img src="https://s3.amazonaws.com/cdn.freshdesk.com/attachments/membership_plans_tab.png" 
         alt="Admin navigation to Finance > Membership Plans" />

    <h2>Step 2: Configure Pricing and Sign-Up Rules</h2>
    <p>Choose between Monthly, Quarterly, Semi-Annual, or Annual billing frequencies. You can also set one-time registration fees.</p>
    <img src="https://cdn.freshdesk.com/attachments/membership_pricing_options.png" 
         alt="Pricing options and billing frequencies" />

    <h2>Step 3: Member Privileges and Search Visibility</h2>
    <p>Set search priority, profile fields, and content publishing privileges for each membership tier.</p>
  </article>
</body>
</html>
"""


@pytest.fixture
def pipeline_settings(tmp_path: Path) -> Settings:
    """Fixture providing isolated temporary Settings for end-to-end testing."""
    return Settings(
        base_dir=tmp_path,
        embedding_provider="mock",
        mock_llm=True,
        similarity_threshold=0.10,  # Safe threshold for mock hash embeddings
        confidence_threshold=0.70,
        max_images_per_answer=2,
        auto_index_resolved_escalations=True,
        anthropic_api_key="test-api-key",
    )


# ------------------------------------------------------------------------------
# 1. Full Pipeline: HTML -> Chunking -> Vector DB -> Retrieval -> Claude QA
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_pipeline_crawl_chunk_index_retrieve_synthesize(pipeline_settings: Settings):
    """Verify that an article flows from raw HTML through chunking, ChromaDB, and Claude synthesis."""
    # 1. HTML Extraction
    article_url = "https://support.brilliantdirectories.com/support/solutions/articles/12345-custom-membership-plans"
    parsed = extract_article(
        html=RAW_HTML_ARTICLE,
        source_url=article_url,
        image_whitelist=pipeline_settings.image_domains_whitelist,
    )

    assert "Membership Plans" in parsed.title
    assert parsed.category == "Finance"
    assert len(parsed.images) == 2
    assert "membership_plans_tab.png" in parsed.images[0].url

    # 2. Build ArticleRecord
    article_record = ArticleRecord(
        url=article_url,
        title=parsed.title,
        category=parsed.category,
        folder=parsed.folder or "Membership Plans",
        content=parsed.content,
        images=parsed.images,
        content_hash=parsed.content_hash,
        status=ArticleStatus.ACTIVE,
    )

    # 3. Vector Indexing into ChromaDB
    store = VectorStore(
        config=pipeline_settings,
        embedding_fn=MockEmbeddingFunction(),
    )
    indexed_count = store.index_article(article_record)
    assert indexed_count >= 1
    assert store.count() == indexed_count

    # 4. RAG Grounded Query
    escalation_mgr = EscalationManager(config=pipeline_settings)
    engine = RAGEngine(
        config=pipeline_settings,
        vector_store=store,
        escalation_manager=escalation_mgr,
    )

    req = QueryRequest(query="How do I access Finance Membership Plans to manage tiers?", top_k=2)
    response = await engine.answer_query(req)

    # 5. Verify Grounded Answer & Citations
    assert response.escalated is False
    assert response.escalation_id is None
    assert response.confidence_score >= pipeline_settings.confidence_threshold
    assert len(response.sources) >= 1

    top_citation = response.sources[0]
    assert top_citation.url == article_url
    assert top_citation.title == parsed.title
    assert "Membership Plans" in top_citation.snippet

    # 6. Verify Screenshot Preservation Through Entire Pipeline
    assert len(response.images) >= 1
    assert "membership_plans_tab.png" in response.images[0].url


# ------------------------------------------------------------------------------
# 2. Unsupported Inquiries & Persistent Human Escalation
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unsupported_question_creates_persistent_escalation(pipeline_settings: Settings):
    """Unsupported inquiry triggers abstention and persists a human-expert review task."""
    store = VectorStore(
        config=pipeline_settings,
        embedding_fn=MockEmbeddingFunction(),
    )
    escalation_mgr = EscalationManager(config=pipeline_settings)
    engine = RAGEngine(
        config=pipeline_settings,
        vector_store=store,
        escalation_manager=escalation_mgr,
    )

    unsupported_query = "How to integrate proprietary quantum hardware accelerators into BD search?"
    req = QueryRequest(query=unsupported_query, min_score=0.99)
    response = await engine.answer_query(req)

    # Verify abstention response
    assert response.escalated is True
    assert response.escalation_id is not None
    assert response.confidence_score == 0.0

    # Verify task persisted to disk
    task = escalation_mgr.get_escalation(response.escalation_id)
    assert task is not None
    assert task.status == EscalationStatus.PENDING
    assert task.query == unsupported_query
    assert "similarity threshold" in task.reason.lower()

    # Verify task can be retrieved by status
    pending_tasks = escalation_mgr.list_escalations(status=EscalationStatus.PENDING)
    assert any(t.id == task.id for t in pending_tasks)


# ------------------------------------------------------------------------------
# 3. Closed-Loop Human Feedback Learning
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_closed_loop_feedback_auto_indexes_resolution(pipeline_settings: Settings):
    """Resolving an escalation task auto-indexes verified guidance so future queries answer confidently."""
    store = VectorStore(
        config=pipeline_settings,
        embedding_fn=MockEmbeddingFunction(),
    )
    escalation_mgr = EscalationManager(config=pipeline_settings)
    engine = RAGEngine(
        config=pipeline_settings,
        vector_store=store,
        escalation_manager=escalation_mgr,
    )

    # Initial state: query cannot be answered
    initial_query = "What is the procedure for custom multi-tenant sub-account isolation?"
    initial_resp = await engine.answer_query(QueryRequest(query=initial_query, min_score=0.95))
    assert initial_resp.escalated is True
    task_id = initial_resp.escalation_id

    # Expert consultant resolves the escalation
    expert_resolution = (
        "Multi-tenant sub-account isolation in Brilliant Directories requires configuring "
        "sub-accounts under Members > Multi-Member Manager and assigning separate child login credentials."
    )
    resolved_task = escalation_mgr.resolve_escalation(
        task_id=task_id,
        resolution=expert_resolution,
        expert_name="Principal Solution Architect",
    )
    assert resolved_task.status == EscalationStatus.RESOLVED

    # Re-query the same topic
    followup_resp = await engine.answer_query(
        QueryRequest(query="multi-tenant sub-account isolation procedure", min_score=0.10)
    )

    # Verify the system has learned: answered using the auto-indexed expert guidance!
    assert followup_resp.escalated is False
    assert len(followup_resp.sources) >= 1
    assert "Expert Guidance" in followup_resp.sources[0].title
    assert "expert-guidance" in followup_resp.sources[0].url


# ------------------------------------------------------------------------------
# 4. Pipeline Failure Resilience & Error Handling
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_claude_timeout_resilience(pipeline_settings: Settings):
    """Claude API timeouts trigger safe escalation and never crash the service."""
    store = VectorStore(
        config=pipeline_settings,
        embedding_fn=MockEmbeddingFunction(),
    )
    # Index dummy chunk so retrieval passes Tier 1
    store.index_article(
        ArticleRecord(
            url="https://support.brilliantdirectories.com/article/1",
            title="General Settings Overview",
            content="General Settings controls website name, default currency, and timezone.",
            content_hash="mock_hash_general_settings",
            status=ArticleStatus.ACTIVE,
        )
    )

    mock_client = AsyncMock()
    mock_client.messages.create.side_effect = anthropic.APITimeoutError(request=MagicMock())

    pipeline_settings.mock_llm = False
    escalation_mgr = EscalationManager(config=pipeline_settings)
    engine = RAGEngine(
        config=pipeline_settings,
        vector_store=store,
        escalation_manager=escalation_mgr,
        anthropic_client=mock_client,
    )

    req = QueryRequest(query="General settings default currency", min_score=0.01)
    response = await engine.answer_query(req)

    assert response.escalated is True
    assert "timed out" in response.answer.lower()
    task = escalation_mgr.get_escalation(response.escalation_id)
    assert task is not None
    assert "timeout" in task.reason.lower()


def test_fastapi_malformed_requests_and_404_resilience(
    monkeypatch,
    pipeline_settings: Settings,
):
    """FastAPI endpoints handle malformed inputs and non-existent IDs with standard HTTP error codes."""
    monkeypatch.setattr("src.api.settings", pipeline_settings)
    client = TestClient(app)

    # 1. Malformed Query Request (missing query field)
    resp = client.post("/api/v1/query", json={"top_k": 5})
    assert resp.status_code == 422  # Pydantic validation error

    # 2. Malformed Query Request (negative top_k)
    resp = client.post("/api/v1/query", json={"query": "Valid query", "top_k": -1})
    assert resp.status_code == 422

    # 3. Non-existent Escalation Task Detail
    resp = client.get("/api/v1/escalations/esc_nonexistent_999")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()

    # 4. Resolve Non-existent Escalation Task
    resp = client.post(
        "/api/v1/escalations/esc_nonexistent_999/resolve",
        json={"resolution": "Some verified expert feedback.", "expert_name": "Consultant"},
    )
    assert resp.status_code == 404


def test_fastapi_capability_check_endpoint(
    monkeypatch,
    pipeline_settings: Settings,
):
    """Test POST /api/v1/capability-check for Task 3 Meeting-to-Scope integration."""
    monkeypatch.setattr("src.api.settings", pipeline_settings)
    store = VectorStore(config=pipeline_settings, embedding_fn=MockEmbeddingFunction())
    store.index_article(
        ArticleRecord(
            url="https://support.brilliantdirectories.com/support/solutions/articles/12345-membership-plans",
            title="Membership Plans Configuration",
            content="Membership Plans allows website owners to configure recurring billing and tiers in Finance > Membership Plans.",
            content_hash="mock_plans_hash",
            status=ArticleStatus.ACTIVE,
        )
    )

    client = TestClient(app)

    # 1. Native requirement check
    resp = client.post(
        "/api/v1/capability-check",
        json={"requirement": "Configure recurring billing membership tiers"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["supported_natively"] is True
    assert "Membership Plans" in data["matching_feature"]
    assert len(data["documentation_urls"]) >= 1

    # 2. Unsupported requirement check
    unsupported_resp = client.post(
        "/api/v1/capability-check",
        json={"requirement": "Quantum encryption accelerator hardware"},
    )
    assert unsupported_resp.status_code == 200
    unsupported_data = unsupported_resp.json()
    assert unsupported_data["supported_natively"] is False
    assert "custom widget or script development" in unsupported_data["notes"]
