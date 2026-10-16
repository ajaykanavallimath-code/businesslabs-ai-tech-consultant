"""Automated tests for Document Chunking & Vector Storage.

Verifies:
1. Semantic chunking with sliding window and character overlap.
2. Metadata preservation (title, URL, article_id, chunk_index, section).
3. Attached instructional screenshots preservation.
4. Empty and short article edge cases.
5. Persistent ChromaDB storage, duplicate prevention, and re-indexing.
6. Stale chunk pruning on soft-delete / update without affecting unrelated documents.
7. Semantic similarity search ranking and distance-to-score normalization.
8. Database persistence and restart behavior.
9. FastAPI query endpoint integration.
"""

from pathlib import Path
import pytest
import chromadb
from fastapi.testclient import TestClient

from src.config import Settings
from src.models import (
    ArticleRecord,
    ArticleStatus,
    DocumentChunk,
    ImageCitation,
    QueryRequest,
    QueryResponse,
)
from src.chunker import chunk_article, extract_article_id
from src.vector_store import VectorStore, MockEmbeddingFunction
from src.api import app


# ------------------------------------------------------------------------------
# Sample Fixtures
# ------------------------------------------------------------------------------

SAMPLE_ARTICLE = ArticleRecord(
    url="https://support.brilliantdirectories.com/support/solutions/articles/12000065940-guide-1-how-to-connect-a-live-domain-name",
    title="Guide 1. How to Connect a Live Domain Name",
    category="Developer Hub",
    folder="Domain Manager",
    content=(
        "## Connect a Live Domain Name\n\n"
        "A Brilliant Directories website begins on a free directoryup.com address. "
        "A domain owned by the website operator can be connected whenever the site is ready to use its public address.\n\n"
        "The current Domain Manager guides the entire connection through up to four stages: "
        "Choose An Address, Check It, Point Domain, and Switch Over.\n\n"
        "## Connection Choices\n\n"
        "Option 1: Use a domain from my Cloudflare account.\n"
        "Option 2: A domain name I own — connect a domain or true subdomain by adding the record shown by Domain Manager.\n"
        "Option 3: A free address from us — choose a new directoryup.com address.\n\n"
        "## DNS Requirements\n\n"
        "A root domain such as example.com is always connected as www.example.com, and the record for the root itself "
        "depends on the company that runs the domain's DNS. Configure CNAME or A Record pointing to the directory IP."
    ),
    images=[
        ImageCitation(
            url="https://s3.amazonaws.com/cdn.freshdesk.com/attachments/domain-manager.png",
            caption="Domain Manager Setup Wizard",
            context="Step 1: Choose An Address in Domain Manager",
        )
    ],
    lastmod="2026-10-11T08:00:54+00:00",
    content_hash="mockhash123456",
    status=ArticleStatus.ACTIVE,
)


# ------------------------------------------------------------------------------
# 1. Chunking Tests
# ------------------------------------------------------------------------------

def test_extract_article_id():
    """Verify article ID extraction from various Brilliant Directories URL structures."""
    id1 = extract_article_id("https://support.brilliantdirectories.com/support/solutions/articles/12000065940-guide-1")
    assert id1 == "12000065940"

    id2 = extract_article_id("https://support.brilliantdirectories.com/support/solutions/12000001358")
    assert id2 == "12000001358"


def test_chunking_sliding_window_and_overlap():
    """Verify that long content splits into sequential chunks with overlap and deterministic IDs."""
    chunks = chunk_article(
        article=SAMPLE_ARTICLE,
        chunk_size=350,
        chunk_overlap=50,
    )

    assert len(chunks) > 1
    assert chunks[0].chunk_id == "12000065940_c0"
    assert chunks[1].chunk_id == "12000065940_c1"
    assert chunks[0].total_chunks == len(chunks)

    # Check that sequential indices increment
    for idx, c in enumerate(chunks):
        assert c.chunk_index == idx
        assert c.total_chunks == len(chunks)
        assert len(c.content) > 0


def test_chunk_metadata_and_image_preservation():
    """Verify that title, canonical URL, breadcrumbs, and images are preserved on chunks."""
    chunks = chunk_article(
        article=SAMPLE_ARTICLE,
        chunk_size=400,
        chunk_overlap=50,
    )

    for c in chunks:
        assert c.title == "Guide 1. How to Connect a Live Domain Name"
        assert c.url == SAMPLE_ARTICLE.url
        assert c.category == "Developer Hub"
        assert c.folder == "Domain Manager"

    # The Domain Manager screenshot must be attached
    has_image = any(len(c.images) > 0 for c in chunks)
    assert has_image is True
    first_chunk_with_img = next(c for c in chunks if len(c.images) > 0)
    assert "domain-manager.png" in first_chunk_with_img.images[0].url


def test_empty_and_short_article_handling():
    """Verify that empty articles return no chunks and short articles return a single chunk."""
    empty_article = ArticleRecord(
        url="https://example.com/empty",
        title="Empty Guide",
        content="",
        content_hash="emptyhash",
    )
    assert chunk_article(empty_article) == []

    short_article = ArticleRecord(
        url="https://example.com/short",
        title="Short Guide",
        content="This is a brief guide under 100 characters.",
        content_hash="shorthash",
    )
    short_chunks = chunk_article(short_article, chunk_size=500)
    assert len(short_chunks) == 1
    assert short_chunks[0].chunk_index == 0
    assert short_chunks[0].total_chunks == 1


# ------------------------------------------------------------------------------
# 2. Vector Store & Re-Indexing Tests
# ------------------------------------------------------------------------------

def test_vector_store_indexing_and_duplicate_prevention(tmp_path):
    """Test indexing, re-indexing without duplicates, and accurate chunk counting."""
    test_settings = Settings(
        base_dir=tmp_path,
        embedding_provider="mock",
        chunk_size=350,
        chunk_overlap=50,
    )
    store = VectorStore(
        config=test_settings,
        client=chromadb.Client(),  # in-memory for fast unit test
        embedding_fn=MockEmbeddingFunction(),
    )

    # Initial Indexing
    count_1 = store.index_article(SAMPLE_ARTICLE)
    assert count_1 > 1
    assert store.count() == count_1

    # Re-index same article with slightly modified content -> Must REPLACE, NOT DUPLICATE!
    modified_article = SAMPLE_ARTICLE.model_copy(
        update={"content": SAMPLE_ARTICLE.content + "\n\n## Additional Notes\nCheck SSL certificate."}
    )
    count_2 = store.index_article(modified_article)
    assert store.count() == count_2  # Total in DB equals new count, no orphan chunks!


def test_stale_chunk_removal(tmp_path):
    """Verify that deleting an article removes only its chunks and leaves others intact."""
    test_settings = Settings(base_dir=tmp_path, embedding_provider="mock")
    store = VectorStore(
        config=test_settings,
        client=chromadb.Client(),
        embedding_fn=MockEmbeddingFunction(),
    )

    article_a = SAMPLE_ARTICLE
    article_b = ArticleRecord(
        url="https://support.brilliantdirectories.com/support/solutions/articles/2000-other-guide",
        title="Other Guide: Email Notifications",
        content="Configure email alerts in the Admin panel under Emails > Email Templates.",
        content_hash="hashb",
    )

    store.index_article(article_a)
    count_a = store.count()

    store.index_article(article_b)
    count_both = store.count()
    assert count_both > count_a

    # Delete article A
    deleted = store.delete_article_chunks(article_a.url)
    assert deleted == count_a
    # Article B chunks must remain intact
    assert store.count() == count_both - count_a


def test_semantic_retrieval_ranking_and_scores(tmp_path):
    """Verify semantic retrieval ranks the most relevant article highest with valid scores."""
    test_settings = Settings(
        base_dir=tmp_path,
        embedding_provider="mock",
        similarity_threshold=0.01,  # Low threshold to capture mock vector matches
    )
    store = VectorStore(
        config=test_settings,
        client=chromadb.Client(),
        embedding_fn=MockEmbeddingFunction(),
    )

    billing_article = ArticleRecord(
        url="https://support.brilliantdirectories.com/support/solutions/articles/billing-guide",
        title="Stripe Payment Gateways Setup",
        content="Enter your Stripe API keys to enable monthly recurring membership subscriptions and credit card billing.",
        images=[
            ImageCitation(
                url="https://s3.amazonaws.com/stripe.png",
                caption="Stripe Credentials Screen",
            )
        ],
        content_hash="billhash",
    )

    domain_article = SAMPLE_ARTICLE

    store.index_article(billing_article)
    store.index_article(domain_article)

    # Search for billing keywords
    citations = store.search(
        query="Stripe recurring subscriptions credit card billing",
        top_k=2,
        min_score=0.05,
    )

    assert len(citations) >= 1
    top_hit = citations[0]
    assert "Stripe" in top_hit.title
    assert top_hit.score >= 0.05
    assert len(top_hit.images) == 1
    assert "stripe.png" in top_hit.images[0].url


def test_vector_store_persistence_and_restart(tmp_path):
    """Verify that chunks persist on disk and reload accurately after client restart."""
    test_settings = Settings(
        base_dir=tmp_path,
        embedding_provider="mock",
    )

    # 1. Create client, index article, close
    store1 = VectorStore(
        config=test_settings,
        embedding_fn=MockEmbeddingFunction(),
    )
    initial_count = store1.index_article(SAMPLE_ARTICLE)
    assert initial_count > 0

    # 2. Simulate restart: instantiate new VectorStore pointing to same persist directory
    store2 = VectorStore(
        config=test_settings,
        embedding_fn=MockEmbeddingFunction(),
    )
    assert store2.count() == initial_count

    # 3. Query reloaded store
    results = store2.search(query="Domain Manager", top_k=1, min_score=0.01)
    assert len(results) == 1
    assert results[0].title == "Guide 1. How to Connect a Live Domain Name"


# ------------------------------------------------------------------------------
# 3. FastAPI Query Endpoint Integration Test
# ------------------------------------------------------------------------------

def test_api_query_endpoint(monkeypatch, tmp_path):
    """Test POST /api/v1/query returns structured citations and screenshots."""
    monkeypatch.setattr("src.api.settings.base_dir", tmp_path)
    monkeypatch.setattr("src.api.settings.embedding_provider", "mock")
    monkeypatch.setattr("src.api.settings.mock_llm", True)

    store = VectorStore(
        config=Settings(base_dir=tmp_path, embedding_provider="mock"),
        embedding_fn=MockEmbeddingFunction(),
    )
    store.index_article(SAMPLE_ARTICLE)

    # Point FastAPI endpoint to our test vector store
    monkeypatch.setattr("src.api.VectorStore", lambda config: store)

    client = TestClient(app)
    response = client.post(
        "/api/v1/query",
        json={"query": "connect custom domain name", "top_k": 2, "min_score": 0.01},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["escalated"] is False
    assert len(data["sources"]) >= 1
    assert "Guide 1" in data["sources"][0]["title"]
    assert len(data["images"]) >= 1
