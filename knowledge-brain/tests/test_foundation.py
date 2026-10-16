"""Foundation tests for Knowledge Brain service.

Verifies:
1. Settings and environment configuration loading, validation, and path overrides.
2. Pydantic models serialization, validation, and constraints.
3. Health check API endpoint response.
"""

from pathlib import Path
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from src.config import Settings
from src.models import (
    SourceCitation,
    ImageCitation,
    QueryRequest,
    QueryResponse,
    CapabilityCheckRequest,
    CapabilityCheckResponse,
    EscalationTask,
    EscalationStatus,
    EscalationResolveRequest,
    HealthResponse,
)
from src.api import app


def test_settings_initialization_and_defaults(tmp_path):
    """Test that settings load defaults and create required paths."""
    test_settings = Settings(base_dir=tmp_path)
    assert test_settings.kb_api_port == 8000
    assert test_settings.similarity_threshold == 0.60
    assert test_settings.confidence_threshold == 0.70
    assert "brilliantdirectories.com" in test_settings.sitemap_url
    assert test_settings.crawl_concurrency == 5
    assert test_settings.max_images_per_answer == 2
    assert test_settings.auto_index_resolved_escalations is True
    assert test_settings.mock_llm is False

    test_settings.ensure_directories()
    assert test_settings.data_dir.exists()
    assert test_settings.chroma_persist_dir.exists()
    assert test_settings.raw_articles_dir.exists()


def test_settings_custom_path_overrides(tmp_path):
    """Test that custom data and chroma persist directories override defaults."""
    custom_data = tmp_path / "custom_data"
    custom_chroma = tmp_path / "custom_chroma"

    settings = Settings(
        base_dir=tmp_path,
        kb_data_dir=custom_data,
        chroma_persist_path=custom_chroma,
    )
    assert settings.data_dir == custom_data
    assert settings.chroma_persist_dir == custom_chroma

    settings.ensure_directories()
    assert custom_data.exists()
    assert custom_chroma.exists()


def test_settings_numeric_range_validations():
    """Test validation boundaries for ports, thresholds, concurrency, and images."""
    # Invalid port (too high)
    with pytest.raises(ValidationError):
        Settings(kb_api_port=70000)

    # Invalid port (zero or negative)
    with pytest.raises(ValidationError):
        Settings(kb_api_port=0)

    # Invalid similarity threshold (> 1.0)
    with pytest.raises(ValidationError):
        Settings(similarity_threshold=1.5)

    # Invalid similarity threshold (< 0.0)
    with pytest.raises(ValidationError):
        Settings(similarity_threshold=-0.1)

    # Invalid confidence threshold (> 1.0)
    with pytest.raises(ValidationError):
        Settings(confidence_threshold=1.05)

    # Invalid crawl concurrency (> 20)
    with pytest.raises(ValidationError):
        Settings(crawl_concurrency=25)

    # Invalid max images (> 5)
    with pytest.raises(ValidationError):
        Settings(max_images_per_answer=10)


def test_settings_url_and_log_level_validations():
    """Test validators for sitemap URL format and logging level."""
    # Invalid sitemap protocol
    with pytest.raises(ValidationError):
        Settings(sitemap_url="ftp://support.brilliantdirectories.com/sitemap.xml")

    # Invalid log level
    with pytest.raises(ValidationError):
        Settings(log_level="VERBOSE_INVALID")

    # Valid lowercase log level converted to uppercase
    valid_settings = Settings(log_level="debug")
    assert valid_settings.log_level == "DEBUG"


def test_models_source_and_image_citations():
    """Test citation schemas and validation."""
    source = SourceCitation(
        title="Settings: General Setup",
        url="https://support.brilliantdirectories.com/support/solutions/articles/123",
        section="Member Photos",
        snippet="Set dimensions in the photo upload field.",
        score=0.88,
    )
    assert source.score == 0.88
    assert source.title == "Settings: General Setup"

    # Score must be between 0.0 and 1.0
    with pytest.raises(ValidationError):
        SourceCitation(
            title="Invalid Score",
            url="https://example.com",
            snippet="Test",
            score=1.5,
        )

    img = ImageCitation(
        url="https://s3.amazonaws.com/example/screenshot.png",
        caption="Photo upload settings",
        context="Step 1: Open General Settings",
    )
    assert "screenshot.png" in img.url
    assert img.caption == "Photo upload settings"


def test_query_response_serialization():
    """Test query response model with citations and images."""
    response = QueryResponse(
        query="How do I set member photo size?",
        answer="Navigate to Settings > General Settings.",
        confidence_score=0.92,
        escalated=False,
        sources=[
            SourceCitation(
                title="Photo Settings",
                url="https://support.brilliantdirectories.com/articles/1",
                snippet="Change dimensions here.",
                score=0.92,
            )
        ],
        images=[
            ImageCitation(
                url="https://example.com/step1.png",
                caption="Settings page",
            )
        ],
    )
    data = response.model_dump()
    assert data["escalated"] is False
    assert len(data["sources"]) == 1
    assert len(data["images"]) == 1


def test_capability_check_model():
    """Test model used by Task 3 (Meeting-to-Scope) for native BD settings."""
    cap = CapabilityCheckResponse(
        requirement="Charge recurring subscriptions",
        supported_natively=True,
        confidence=0.95,
        matching_feature="Membership Plans",
        configuration_path="Finance > Membership Plans",
        documentation_urls=["https://support.brilliantdirectories.com/articles/billing"],
        notes="Native feature via Stripe/PayPal.",
    )
    assert cap.supported_natively is True
    assert cap.confidence == 0.95


def test_escalation_lifecycle_models():
    """Test escalation creation and resolution flow models."""
    task = EscalationTask(
        id="esc-001",
        query="Custom webhook authentication format",
        reason="No documentation found for secret key verification",
        status=EscalationStatus.PENDING,
    )
    assert task.status == EscalationStatus.PENDING
    assert task.resolution is None

    resolve_req = EscalationResolveRequest(
        resolution="Use HMAC SHA-256 header validation on incoming payload.",
        expert_name="Senior BD Consultant",
    )
    assert len(resolve_req.resolution) > 10


def test_health_check_endpoint():
    """Test the FastAPI /api/v1/health endpoint."""
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "Knowledge Brain"
    assert data["version"] == "0.1.0"
