"""
Tests for Task 1 Knowledge Brain integration client.
Verifies request construction, response mapping, citation preservation,
timeout handling, error recovery, and offline mock behavior.
"""

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from src.kb_client import KnowledgeBrainClient
from src.models import CapabilityStatus


@pytest.mark.asyncio
async def test_kb_client_offline_mock_supported():
    """Verify offline mock correctly identifies native features with documentation URLs."""
    client = KnowledgeBrainClient(mock_mode=True)
    res = await client.check_capability("REQ-001", "We need automated monthly billing with Stripe.")
    assert res.status == CapabilityStatus.SUPPORTED
    assert "Stripe" in (res.native_feature_name or "")
    assert len(res.documentation_urls) > 0
    assert "support.brilliantdirectories.com" in res.documentation_urls[0]
    assert res.requires_expert_review is False


@pytest.mark.asyncio
async def test_kb_client_offline_mock_unsupported():
    """Verify offline mock identifies unsupported features and marks expert review."""
    client = KnowledgeBrainClient(mock_mode=True)
    res = await client.check_capability("REQ-002", "We want a native mobile app for iOS and Android on the App Store.")
    assert res.status == CapabilityStatus.UNSUPPORTED
    assert res.recommended_approach == "custom_development"
    assert res.requires_expert_review is True


@pytest.mark.asyncio
async def test_kb_client_capability_check_endpoint_success():
    """Verify live-mode HTTP request construction and response parsing for /api/v1/capability-check."""
    client = KnowledgeBrainClient(base_url="http://localhost:8000", mock_mode=False)

    fake_response = {
        "requirement": "Stripe recurring billing",
        "supported_natively": True,
        "confidence": 0.95,
        "matching_feature": "Stripe Payment Gateway",
        "configuration_path": "Finance > Payment Settings",
        "documentation_urls": ["https://support.brilliantdirectories.com/article/stripe"],
        "notes": "Native Stripe integration with webhooks.",
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_response

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=mock_resp):
        res = await client.check_capability("REQ-001", "Stripe recurring billing")
        assert res.status == CapabilityStatus.SUPPORTED
        assert res.native_feature_name == "Stripe Payment Gateway"
        assert res.configuration_path == "Finance > Payment Settings"
        assert len(res.documentation_urls) == 1


@pytest.mark.asyncio
async def test_kb_client_timeout_handling():
    """Verify httpx.TimeoutException is safely caught and returns explainable error assessment."""
    client = KnowledgeBrainClient(base_url="http://localhost:8000", timeout=1.0, mock_mode=False)

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, side_effect=httpx.TimeoutException("Timed out")):
        res = await client.check_capability("REQ-001", "Stripe payment")
        assert res.status == CapabilityStatus.NEEDS_EXPERT_REVIEW
        assert res.requires_expert_review is True
        assert "timed out" in res.evidence_summary.lower()


@pytest.mark.asyncio
async def test_kb_client_query_fallback():
    """Verify fallback to /api/v1/query when /api/v1/capability-check returns 404."""
    client = KnowledgeBrainClient(base_url="http://localhost:8000", mock_mode=False)

    # First call returns 404, fallback query returns 200 with citations
    resp_404 = MagicMock(status_code=404)
    resp_query = MagicMock()
    resp_query.status_code = 200
    resp_query.json.return_value = {
        "query": "Is this feature supported in Brilliant Directories: Custom Search?",
        "answer": "Yes, Brilliant Directories supports custom radius search natively.",
        "confidence_score": 0.88,
        "escalated": False,
        "sources": [{"title": "Radius Search", "url": "https://support.brilliantdirectories.com/article/search"}],
    }

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock, side_effect=[resp_404, resp_query]):
        res = await client.check_capability("REQ-001", "Custom Search")
        assert res.status == CapabilityStatus.SUPPORTED
        assert len(res.documentation_urls) == 1

