"""Tests for Step 1.4: Claude RAG Engine with Strict Citations & Escalation."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import anthropic
import pytest
from fastapi.testclient import TestClient

from src.api import app
from src.config import Settings
from src.escalation_manager import EscalationManager
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

SAMPLE_ARTICLE = ArticleRecord(
    url="https://support.brilliantdirectories.com/support/solutions/articles/12345-how-to-connect-domain",
    title="How to Connect a Custom Live Domain Name",
    category="Domains & Hosting",
    folder="Domain Manager",
    content=(
        "## Connect a Live Domain Name\n\n"
        "To connect your custom live domain name in Brilliant Directories, follow these steps:\n"
        "1. Log into your Brilliant Directories Admin Dashboard.\n"
        "2. Navigate to Settings > Domain Manager.\n"
        "3. Enter your primary domain name (e.g., example.com).\n"
        "4. Update your A Record with your domain registrar to point to the BD server IP address: 123.45.67.89.\n"
        "5. Allow 24 to 48 hours for global DNS propagation to complete.\n"
        "Once propagation completes, your SSL certificate will automatically generate."
    ),
    images=[
        ImageCitation(
            url="https://s3.amazonaws.com/cdn.freshdesk.com/attachments/domain_manager_tab.png",
            caption="Domain Manager Setup Wizard",
            context="Step 1: Domain Manager",
        ),
        ImageCitation(
            url="https://cdn.freshdesk.com/attachments/dns_a_record_setup.png",
            caption="DNS A Record Configuration",
            context="Step 4: DNS Setup",
        ),
    ],
    lastmod="2025-01-15T08:00:00Z",
    content_hash="mockhash_sample_rag_article",
    status=ArticleStatus.ACTIVE,
)


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    """Fixture providing isolated temporary Settings for RAG tests."""
    return Settings(
        base_dir=tmp_path,
        embedding_provider="mock",
        mock_llm=True,
        similarity_threshold=0.10,  # Safe threshold for mock hash embeddings in unit tests
        confidence_threshold=0.70,
        max_images_per_answer=2,
        anthropic_api_key="test-api-key",
    )


@pytest.fixture
def populated_vector_store(test_settings: Settings) -> VectorStore:
    """Fixture providing VectorStore with indexed sample article."""
    store = VectorStore(
        config=test_settings,
        embedding_fn=MockEmbeddingFunction(),
    )
    store.index_article(SAMPLE_ARTICLE)
    return store


# ------------------------------------------------------------------------------
# 1. Grounded QA & Strict Citations
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_supported_query_grounded_answer_and_citations(
    test_settings: Settings,
    populated_vector_store: VectorStore,
):
    """Supported questions produce answers with valid source citations and images."""
    engine = RAGEngine(
        config=test_settings,
        vector_store=populated_vector_store,
        escalation_manager=EscalationManager(config=test_settings),
    )

    req = QueryRequest(query="How do I connect my live custom domain name?", top_k=2)
    response = await engine.answer_query(req)

    assert response.escalated is False
    assert response.escalation_id is None
    assert response.confidence_score >= test_settings.confidence_threshold
    assert len(response.sources) >= 1

    # Verify citation fields
    top_source = response.sources[0]
    assert top_source.url == SAMPLE_ARTICLE.url
    assert top_source.title == SAMPLE_ARTICLE.title
    assert "Domain Manager" in top_source.snippet

    # Verify article images preserved
    assert len(response.images) >= 1
    assert "freshdesk.com" in response.images[0].url


@pytest.mark.asyncio
async def test_every_citation_points_to_actual_retrieved_source(
    test_settings: Settings,
    populated_vector_store: VectorStore,
):
    """Every citation in response.sources MUST map to an actual retrieved chunk."""
    engine = RAGEngine(
        config=test_settings,
        vector_store=populated_vector_store,
        escalation_manager=EscalationManager(config=test_settings),
    )

    req = QueryRequest(query="Connect custom domain A record settings", top_k=3)
    response = await engine.answer_query(req)

    # All citations must correspond to the indexed sample article URL
    for citation in response.sources:
        assert citation.url == SAMPLE_ARTICLE.url
        assert citation.title == SAMPLE_ARTICLE.title
        assert citation.score > 0.0


# ------------------------------------------------------------------------------
# 2. Insufficient Evidence, Abstention & Human Escalation
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unsupported_query_triggers_abstention_and_escalation(
    test_settings: Settings,
    populated_vector_store: VectorStore,
):
    """Unsupported questions trigger abstention and create a persistent escalation task."""
    escalation_mgr = EscalationManager(config=test_settings)
    engine = RAGEngine(
        config=test_settings,
        vector_store=populated_vector_store,
        escalation_manager=escalation_mgr,
    )

    # "quantum" keyword activates simulated abstention policy in mock LLM
    req = QueryRequest(query="How to connect domain with unsupported quantum setup?", min_score=0.01)
    response = await engine.answer_query(req)

    assert response.escalated is True
    assert response.escalation_id is not None
    assert response.escalation_id.startswith("esc_")
    assert "Escalated to human expert" in response.answer

    # Verify task was persisted to escalations.json
    task = escalation_mgr.get_escalation(response.escalation_id)
    assert task is not None
    assert task.id == response.escalation_id
    assert task.status == EscalationStatus.PENDING
    assert task.query == req.query
    assert "unsupported" in task.reason.lower()


@pytest.mark.asyncio
async def test_low_retrieval_similarity_tier1_escalation(
    test_settings: Settings,
    populated_vector_store: VectorStore,
):
    """Queries that yield no chunks above min_score trigger immediate Tier 1 escalation."""
    escalation_mgr = EscalationManager(config=test_settings)
    engine = RAGEngine(
        config=test_settings,
        vector_store=populated_vector_store,
        escalation_manager=escalation_mgr,
    )

    # Impossibly high similarity threshold
    req = QueryRequest(
        query="Random unindexed topic",
        min_score=0.999,
    )
    response = await engine.answer_query(req)

    assert response.escalated is True
    assert response.escalation_id is not None
    assert response.confidence_score == 0.0
    assert "could not find verified Brilliant Directories documentation" in response.answer

    # Verify escalation task reason mentions threshold
    task = escalation_mgr.get_escalation(response.escalation_id)
    assert task is not None
    assert "similarity threshold" in task.reason.lower()


@pytest.mark.asyncio
async def test_low_confidence_score_below_cutoff_triggers_escalation(
    test_settings: Settings,
    populated_vector_store: VectorStore,
):
    """Uncalibrated or weak LLM confidence (< threshold) triggers escalation."""
    escalation_mgr = EscalationManager(config=test_settings)
    engine = RAGEngine(
        config=test_settings,
        vector_store=populated_vector_store,
        escalation_manager=escalation_mgr,
    )

    # Triggers low confidence simulation (0.45 < 0.70 threshold)
    req = QueryRequest(query="Domain Manager settings with low confidence", min_score=0.01)
    response = await engine.answer_query(req)

    assert response.escalated is True
    assert response.escalation_id is not None
    assert response.confidence_score < test_settings.confidence_threshold


# ------------------------------------------------------------------------------
# 3. Anti-Hallucination & Citation Verification
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_anti_hallucination_rejects_invented_citation_urls(
    test_settings: Settings,
    populated_vector_store: VectorStore,
):
    """If Claude outputs hallucinated citation URLs not in retrieved context, reject & escalate."""
    escalation_mgr = EscalationManager(config=test_settings)
    engine = RAGEngine(
        config=test_settings,
        vector_store=populated_vector_store,
        escalation_manager=escalation_mgr,
    )

    # Triggers hallucinated citation simulation in mock LLM
    req = QueryRequest(query="Domain Manager settings that hallucinate citation", min_score=0.01)
    response = await engine.answer_query(req)

    assert response.escalated is True
    assert response.escalation_id is not None
    assert response.confidence_score == 0.0

    task = escalation_mgr.get_escalation(response.escalation_id)
    assert task is not None
    assert "hallucinated" in task.reason.lower() or "unverified" in task.reason.lower()


# ------------------------------------------------------------------------------
# 4. Error & Timeout Resilience
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_claude_api_error_does_not_crash_service(
    test_settings: Settings,
    populated_vector_store: VectorStore,
):
    """Claude API failure (e.g. connection error) safely escalates without crashing."""
    escalation_mgr = EscalationManager(config=test_settings)
    engine = RAGEngine(
        config=test_settings,
        vector_store=populated_vector_store,
        escalation_manager=escalation_mgr,
    )

    # Triggers error simulation in mock LLM
    req = QueryRequest(query="Domain Manager settings simulate error in API", min_score=0.01)
    response = await engine.answer_query(req)

    assert response.escalated is True
    assert response.escalation_id is not None
    assert "error" in response.answer.lower()

    task = escalation_mgr.get_escalation(response.escalation_id)
    assert task is not None
    assert "error" in task.reason.lower()


@pytest.mark.asyncio
async def test_missing_api_key_safely_escalates(
    test_settings: Settings,
    populated_vector_store: VectorStore,
):
    """Missing Anthropic API key when mock_llm=False safely escalates."""
    no_key_settings = Settings(
        base_dir=test_settings.base_dir,
        embedding_provider="mock",
        mock_llm=False,
        similarity_threshold=0.20,
        anthropic_api_key="",  # Empty credentials
    )
    escalation_mgr = EscalationManager(config=no_key_settings)
    engine = RAGEngine(
        config=no_key_settings,
        vector_store=populated_vector_store,
        escalation_manager=escalation_mgr,
    )

    req = QueryRequest(query="How to configure domain?")
    response = await engine.answer_query(req)

    assert response.escalated is True
    assert response.escalation_id is not None
    assert "unconfigured" in response.answer.lower()

    task = escalation_mgr.get_escalation(response.escalation_id)
    assert task is not None
    assert "API key" in task.reason


@pytest.mark.asyncio
async def test_mocked_claude_async_client_grounded_success(
    test_settings: Settings,
    populated_vector_store: VectorStore,
):
    """Test full Claude JSON response parsing using a mocked AsyncAnthropic client."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_content_block = MagicMock()

    # Model returns compliant structured JSON
    grounded_json = json.dumps({
        "answer": "To connect a domain, go to Settings > Domain Manager and point your A Record. [Source: How to Connect a Custom Live Domain Name]",
        "abstain": False,
        "confidence": 0.95,
        "cited_urls": [SAMPLE_ARTICLE.url],
        "selected_image_urls": [SAMPLE_ARTICLE.images[0].url],
        "escalation_reason": None,
    })
    mock_content_block.text = grounded_json
    mock_response.content = [mock_content_block]
    mock_client.messages.create.return_value = mock_response

    # Force mock_llm=False so the client is invoked
    test_settings.mock_llm = False
    engine = RAGEngine(
        config=test_settings,
        vector_store=populated_vector_store,
        escalation_manager=EscalationManager(config=test_settings),
        anthropic_client=mock_client,
    )

    req = QueryRequest(query="How to connect live domain?")
    response = await engine.answer_query(req)

    assert response.escalated is False
    assert response.confidence_score == 0.95
    assert "Settings > Domain Manager" in response.answer
    assert len(response.sources) == 1
    assert response.sources[0].url == SAMPLE_ARTICLE.url
    assert len(response.images) == 1
    assert response.images[0].url == SAMPLE_ARTICLE.images[0].url


@pytest.mark.asyncio
async def test_mocked_claude_timeout_triggers_escalation(
    test_settings: Settings,
    populated_vector_store: VectorStore,
):
    """Test that an anthropic.APITimeoutError triggers safe escalation."""
    mock_client = AsyncMock()
    # Mock timeout error
    mock_client.messages.create.side_effect = anthropic.APITimeoutError(
        request=MagicMock()
    )

    test_settings.mock_llm = False
    escalation_mgr = EscalationManager(config=test_settings)
    engine = RAGEngine(
        config=test_settings,
        vector_store=populated_vector_store,
        escalation_manager=escalation_mgr,
        anthropic_client=mock_client,
    )

    req = QueryRequest(query="How to configure domain?")
    response = await engine.answer_query(req)

    assert response.escalated is True
    assert response.escalation_id is not None
    assert "timed out" in response.answer.lower()

    task = escalation_mgr.get_escalation(response.escalation_id)
    assert task is not None
    assert "timeout" in task.reason.lower()


# ------------------------------------------------------------------------------
# 5. Escalation Task Lifecycle & Human-in-the-Loop Resolution
# ------------------------------------------------------------------------------

def test_escalation_manager_create_list_resolve(test_settings: Settings):
    """Test full escalation lifecycle: create, list, retrieve, and resolve."""
    mgr = EscalationManager(config=test_settings)

    # 1. Create escalation
    task = mgr.create_escalation(
        query="Can I connect multiple primary domains?",
        reason="Solution Center states only 1 primary domain supported natively.",
        sources=[
            SourceCitation(
                article_id="12345",
                title=SAMPLE_ARTICLE.title,
                url=SAMPLE_ARTICLE.url,
                snippet="Step 1: Domain Manager setup wizard instructions.",
                score=0.82,
            )
        ],
    )
    assert task.status == EscalationStatus.PENDING
    assert task.resolved_at is None

    # 2. List escalations
    pending = mgr.list_escalations(status=EscalationStatus.PENDING)
    assert len(pending) == 1
    assert pending[0].id == task.id

    # 3. Resolve escalation
    resolved_task = mgr.resolve_escalation(
        task_id=task.id,
        resolution="Brilliant Directories only supports one primary live domain. Domain aliases can be parked via registrar DNS.",
        expert_name="Senior BD Consultant",
    )
    assert resolved_task is not None
    assert resolved_task.status == EscalationStatus.RESOLVED
    assert resolved_task.resolved_at is not None
    assert resolved_task.expert_name == "Senior BD Consultant"

    # 4. Verify disk persistence across new manager instance
    mgr2 = EscalationManager(config=test_settings)
    fetched = mgr2.get_escalation(task.id)
    assert fetched is not None
    assert fetched.status == EscalationStatus.RESOLVED
    assert fetched.resolution == resolved_task.resolution


# ------------------------------------------------------------------------------
# 6. FastAPI REST Endpoints & Documentation Schemas
# ------------------------------------------------------------------------------

def test_fastapi_query_and_escalation_endpoints(
    monkeypatch,
    test_settings: Settings,
    populated_vector_store: VectorStore,
):
    """Test FastAPI /api/v1/query and /api/v1/escalations REST API endpoints."""
    monkeypatch.setattr("src.api.settings", test_settings)

    client = TestClient(app)

    # 1. POST /api/v1/query (Supported Query)
    resp = client.post(
        "/api/v1/query",
        json={"query": "How do I connect my live custom domain?", "top_k": 2},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["escalated"] is False
    assert len(data["sources"]) >= 1
    assert data["sources"][0]["title"] == SAMPLE_ARTICLE.title

    # 2. POST /api/v1/query (Unsupported Query -> Escalation)
    esc_resp = client.post(
        "/api/v1/query",
        json={"query": "How to implement quantum encryption?"},
    )
    assert esc_resp.status_code == 200
    esc_data = esc_resp.json()
    assert esc_data["escalated"] is True
    assert esc_data["escalation_id"] is not None
    task_id = esc_data["escalation_id"]

    # 3. GET /api/v1/escalations
    list_resp = client.get("/api/v1/escalations")
    assert list_resp.status_code == 200
    tasks = list_resp.json()
    assert any(t["id"] == task_id for t in tasks)

    # 4. GET /api/v1/escalations/{task_id}
    detail_resp = client.get(f"/api/v1/escalations/{task_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["id"] == task_id

    # 5. POST /api/v1/escalations/{task_id}/resolve
    resolve_resp = client.post(
        f"/api/v1/escalations/{task_id}/resolve",
        json={
            "resolution": "Quantum encryption is not supported by Brilliant Directories webhooks.",
            "expert_name": "Consultant Alice",
        },
    )
    assert resolve_resp.status_code == 200
    resolved_data = resolve_resp.json()
    assert resolved_data["status"] == "resolved"
    assert resolved_data["resolution"] == "Quantum encryption is not supported by Brilliant Directories webhooks."
    assert resolved_data["expert_name"] == "Consultant Alice"

    # 6. GET 404 for unknown task
    not_found = client.get("/api/v1/escalations/esc_nonexistent")
    assert not_found.status_code == 404
