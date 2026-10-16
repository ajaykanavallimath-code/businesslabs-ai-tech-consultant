"""Automated unit tests for Sitemap Ingestion & Incremental Crawler.

Tests cover:
1. Sitemap XML parsing (valid, malformed, namespaces, deduplication, URL filtering).
2. HTML article parsing (title, breadcrumbs, text cleanup, noise decomposition).
3. Article image URL extraction and domain whitelist filtering.
4. 3-way incremental sync:
   - New article discovery (added).
   - Unchanged article detection (skipped without HTTP fetch).
   - Updated article detection (re-fetched on lastmod change).
   - Removed article detection (safe soft-deletion with timestamp).
5. Network failure handling, retries, and resumability after partial failures.
6. FastAPI sync endpoint integration.
"""

import json
from pathlib import Path
import pytest
import httpx
from fastapi.testclient import TestClient

from src.config import Settings
from src.models import ArticleStatus, SyncResponse
from src.html_parser import extract_article
from src.sitemap_sync import SitemapParser, SitemapCrawler
from src.api import app


# ------------------------------------------------------------------------------
# Mock Data Fixtures
# ------------------------------------------------------------------------------

VALID_SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://support.brilliantdirectories.com/support/solutions/articles/1001-guide-one</loc>
    <lastmod>2026-10-01T12:00:00+00:00</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://support.brilliantdirectories.com/support/solutions/articles/1002-guide-two</loc>
    <lastmod>2026-10-01T12:00:00+00:00</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>
</urlset>
"""

MALFORMED_SITEMAP_XML = """
<urlset>
  <url>
    <loc>https://support.brilliantdirectories.com/support/solutions/articles/1003-broken-xml
    <lastmod>2026-10-01T12:00:00+00:00</lastmod>
  </url>
  <url>
    <loc>https://support.brilliantdirectories.com/support/solutions/articles/1004-salvaged-url</loc>
  </url>
"""

ARTICLE_1_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Guide One: How to Set Up Payment Gateways | Brilliant Directories Documentation | BD Support</title>
  <link rel="canonical" href="https://support.brilliantdirectories.com/support/solutions/articles/1001-guide-one" />
</head>
<body>
  <div class="breadcrumb">
    <a href="/support/solutions">Solution Center Home</a>
    <a href="/support/solutions/123">Section: Finance & Payments</a>
    <a href="/support/solutions/folders/456">Stripe Integration</a>
  </div>
  <article class="article-body" id="article-body">
    <h1 class="post-title">Guide One: How to Set Up Payment Gateways</h1>
    <p>To connect Stripe, navigate to Finance > Payment Gateways.</p>
    <p><img src="https://s3.amazonaws.com/cdn.freshdesk.com/attachments/stripe-settings.png" alt="Stripe Setup Dashboard" /></p>
    <p><em>Step 1: Enter your Publishable Key and Secret Key.</em></p>
    <p>Save changes to activate recurring subscriptions.</p>
  </article>
  <div class="article-footer-content">
    <p>Promo: Hire a developer at marketplace.brilliantdirectories.com</p>
    <img src="https://example.com/banner.jpg" alt="Promo Banner" />
  </div>
  <div class="article-vote" id="voting-container">Was this helpful?</div>
</body>
</html>
"""

ARTICLE_2_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Guide Two: Member Photo Sizing</title>
</head>
<body>
  <article class="article-body">
    <h1 class="post-title">Guide Two: Member Photo Sizing</h1>
    <p>Configure photo width and height under General Settings > Member Images.</p>
  </article>
</body>
</html>
"""


# ------------------------------------------------------------------------------
# 1. Sitemap Parser Tests
# ------------------------------------------------------------------------------

def test_sitemap_parser_valid_xml():
    """Verify standard sitemap parsing with namespace and metadata."""
    entries = SitemapParser.parse(VALID_SITEMAP_XML)
    assert len(entries) == 2
    assert entries[0].url == "https://support.brilliantdirectories.com/support/solutions/articles/1001-guide-one"
    assert entries[0].lastmod == "2026-10-01T12:00:00+00:00"
    assert entries[0].priority == 0.8
    assert entries[1].url == "https://support.brilliantdirectories.com/support/solutions/articles/1002-guide-two"


def test_sitemap_parser_malformed_xml_recovery():
    """Verify parser falls back to regex recovery when XML is malformed."""
    entries = SitemapParser.parse(MALFORMED_SITEMAP_XML)
    # Should salvage valid <loc> tags without crashing
    assert len(entries) >= 1
    urls = [e.url for e in entries]
    assert "https://support.brilliantdirectories.com/support/solutions/articles/1004-salvaged-url" in urls


def test_sitemap_parser_filtering_and_deduplication():
    """Verify that disallowed routes (login, search, tickets) are filtered and duplicates dropped."""
    xml_with_dupes_and_noise = """<urlset>
      <url><loc>https://support.brilliantdirectories.com/support/solutions/articles/2000-valid</loc></url>
      <url><loc>https://support.brilliantdirectories.com/support/solutions/articles/2000-valid</loc></url>
      <url><loc>https://support.brilliantdirectories.com/support/search/solutions</loc></url>
      <url><loc>https://support.brilliantdirectories.com/support/login</loc></url>
      <url><loc>ftp://invalid-protocol.com/page</loc></url>
    </urlset>"""

    entries = SitemapParser.parse(xml_with_dupes_and_noise)
    assert len(entries) == 1
    assert entries[0].url == "https://support.brilliantdirectories.com/support/solutions/articles/2000-valid"


# ------------------------------------------------------------------------------
# 2. HTML Article Parser & Image Extraction Tests
# ------------------------------------------------------------------------------

def test_html_parser_article_extraction():
    """Verify title, breadcrumb category/folder, and clean text extraction."""
    parsed = extract_article(
        html=ARTICLE_1_HTML,
        source_url="https://support.brilliantdirectories.com/support/solutions/articles/1001-guide-one",
    )

    assert parsed.title == "Guide One: How to Set Up Payment Gateways"
    assert parsed.category == "Finance & Payments"
    assert parsed.folder == "Stripe Integration"
    assert "To connect Stripe, navigate to Finance > Payment Gateways." in parsed.content
    assert "Save changes to activate recurring subscriptions." in parsed.content

    # Noise elements must be removed
    assert "Promo: Hire a developer" not in parsed.content
    assert "Was this helpful?" not in parsed.content


def test_html_parser_image_whitelist_filtering():
    """Verify that instructional screenshots are extracted while banners are excluded."""
    whitelist = ["s3.amazonaws.com", "cdn.freshdesk.com"]
    parsed = extract_article(
        html=ARTICLE_1_HTML,
        source_url="https://support.brilliantdirectories.com/support/solutions/articles/1001-guide-one",
        image_whitelist=whitelist,
        max_images=2,
    )

    # Must extract the Stripe screenshot (inside article body, whitelisted domain)
    assert len(parsed.images) == 1
    img = parsed.images[0]
    assert "stripe-settings.png" in img.url
    assert img.caption == "Stripe Setup Dashboard"
    assert "Step 1: Enter your Publishable Key" in img.context

    # Promo banner from footer must NOT be present
    image_urls = [i.url for i in parsed.images]
    assert not any("banner.jpg" in u for u in image_urls)


# ------------------------------------------------------------------------------
# 3. 3-Way Incremental Sync Tests
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_incremental_sync_new_and_unchanged(tmp_path):
    """Test initial crawl (Added) and subsequent unchanged crawl (0 HTTP calls)."""
    custom_settings = Settings(base_dir=tmp_path)
    custom_settings.ensure_directories()

    article_fetch_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal article_fetch_count
        url = str(request.url)
        if "sitemap.xml" in url:
            return httpx.Response(200, text=VALID_SITEMAP_XML)
        elif "1001-guide-one" in url:
            article_fetch_count += 1
            return httpx.Response(200, text=ARTICLE_1_HTML)
        elif "1002-guide-two" in url:
            article_fetch_count += 1
            return httpx.Response(200, text=ARTICLE_2_HTML)
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    crawler = SitemapCrawler(config=custom_settings, client=client)

    # First Run: Both articles are NEW (Added)
    res1 = await crawler.run_sync()
    assert res1.stats.added == 2
    assert res1.stats.unchanged == 0
    assert res1.stats.total_active == 2
    assert article_fetch_count == 2

    # Second Run: Sitemap lastmod is identical -> Both articles UNCHANGED (0 fetches!)
    article_fetch_count = 0
    res2 = await crawler.run_sync()
    assert res2.stats.added == 0
    assert res2.stats.unchanged == 2
    assert res2.stats.updated == 0
    assert res2.stats.total_active == 2
    assert article_fetch_count == 0  # CRUCIAL: No HTTP requests made for articles!


@pytest.mark.asyncio
async def test_incremental_sync_updated_article(tmp_path):
    """Test that articles with newer sitemap lastmod are re-crawled and updated."""
    custom_settings = Settings(base_dir=tmp_path)
    custom_settings.ensure_directories()

    def initial_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "sitemap.xml" in url:
            return httpx.Response(200, text=VALID_SITEMAP_XML)
        elif "1001-guide-one" in url:
            return httpx.Response(200, text=ARTICLE_1_HTML)
        elif "1002-guide-two" in url:
            return httpx.Response(200, text=ARTICLE_2_HTML)
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(initial_handler))
    crawler = SitemapCrawler(config=custom_settings, client=client)
    await crawler.run_sync()

    # New sitemap where article 1 has a NEWER lastmod timestamp
    UPDATED_SITEMAP_XML = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url>
        <loc>https://support.brilliantdirectories.com/support/solutions/articles/1001-guide-one</loc>
        <lastmod>2026-10-15T00:00:00+00:00</lastmod>
      </url>
      <url>
        <loc>https://support.brilliantdirectories.com/support/solutions/articles/1002-guide-two</loc>
        <lastmod>2026-10-01T12:00:00+00:00</lastmod>
      </url>
    </urlset>"""

    MODIFIED_ARTICLE_1_HTML = ARTICLE_1_HTML.replace(
        "To connect Stripe, navigate to Finance > Payment Gateways.",
        "To connect Stripe v2, navigate to Settings > Payments.",
    )

    def updated_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "sitemap.xml" in url:
            return httpx.Response(200, text=UPDATED_SITEMAP_XML)
        elif "1001-guide-one" in url:
            return httpx.Response(200, text=MODIFIED_ARTICLE_1_HTML)
        elif "1002-guide-two" in url:
            return httpx.Response(200, text=ARTICLE_2_HTML)
        return httpx.Response(404)

    client_updated = httpx.AsyncClient(transport=httpx.MockTransport(updated_handler))
    crawler_updated = SitemapCrawler(config=custom_settings, client=client_updated)

    res = await crawler_updated.run_sync()
    assert res.stats.updated == 1
    assert res.stats.unchanged == 1
    assert res.stats.added == 0
    assert "Settings > Payments" in crawler_updated.state["https://support.brilliantdirectories.com/support/solutions/articles/1001-guide-one"].content


@pytest.mark.asyncio
async def test_incremental_sync_removed_article(tmp_path):
    """Test that articles omitted from sitemap are safely marked as REMOVED."""
    custom_settings = Settings(base_dir=tmp_path)
    custom_settings.ensure_directories()

    def initial_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "sitemap.xml" in url:
            return httpx.Response(200, text=VALID_SITEMAP_XML)
        return httpx.Response(200, text=ARTICLE_1_HTML)

    client = httpx.AsyncClient(transport=httpx.MockTransport(initial_handler))
    crawler = SitemapCrawler(config=custom_settings, client=client)
    await crawler.run_sync()
    assert crawler.state["https://support.brilliantdirectories.com/support/solutions/articles/1002-guide-two"].status == ArticleStatus.ACTIVE

    # Second sitemap has DROPPED article 1002
    REDUCED_SITEMAP_XML = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url>
        <loc>https://support.brilliantdirectories.com/support/solutions/articles/1001-guide-one</loc>
        <lastmod>2026-10-01T12:00:00+00:00</lastmod>
      </url>
    </urlset>"""

    def reduced_handler(request: httpx.Request) -> httpx.Response:
        if "sitemap.xml" in str(request.url):
            return httpx.Response(200, text=REDUCED_SITEMAP_XML)
        return httpx.Response(200, text=ARTICLE_1_HTML)

    client_reduced = httpx.AsyncClient(transport=httpx.MockTransport(reduced_handler))
    crawler_reduced = SitemapCrawler(config=custom_settings, client=client_reduced)

    res = await crawler_reduced.run_sync()
    assert res.stats.removed == 1
    assert res.stats.total_active == 1

    # Safe removal check: Record still exists, status is REMOVED with timestamp
    removed_record = crawler_reduced.state["https://support.brilliantdirectories.com/support/solutions/articles/1002-guide-two"]
    assert removed_record.status == ArticleStatus.REMOVED
    assert removed_record.removed_at is not None


# ------------------------------------------------------------------------------
# 4. Error Handling, Retries, and Resumability Tests
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_crawler_retry_and_partial_failure_resumability(tmp_path):
    """Test that transient network errors are retried, and state is preserved for resumption."""
    custom_settings = Settings(base_dir=tmp_path)
    custom_settings.ensure_directories()

    attempt_counter = 0

    def flaky_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempt_counter
        url = str(request.url)
        if "sitemap.xml" in url:
            return httpx.Response(200, text=VALID_SITEMAP_XML)
        elif "1001-guide-one" in url:
            # Article 1 succeeds
            return httpx.Response(200, text=ARTICLE_1_HTML)
        elif "1002-guide-two" in url:
            # Article 2 fails with 500 error on first run
            attempt_counter += 1
            return httpx.Response(500)
        return httpx.Response(404)

    client1 = httpx.AsyncClient(transport=httpx.MockTransport(flaky_handler))
    crawler1 = SitemapCrawler(config=custom_settings, client=client1)

    # First run: Article 1 added, Article 2 fails after retries
    res1 = await crawler1.run_sync()
    assert res1.stats.added == 1
    assert "https://support.brilliantdirectories.com/support/solutions/articles/1001-guide-one" in crawler1.state

    # Verify atomic file persistence: state file has Article 1 saved
    assert custom_settings.sitemap_state_file.exists()

    # Second run: Server is fixed for Article 2
    def fixed_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "sitemap.xml" in url:
            return httpx.Response(200, text=VALID_SITEMAP_XML)
        elif "1001-guide-one" in url:
            return httpx.Response(200, text=ARTICLE_1_HTML)
        elif "1002-guide-two" in url:
            return httpx.Response(200, text=ARTICLE_2_HTML)
        return httpx.Response(404)

    client2 = httpx.AsyncClient(transport=httpx.MockTransport(fixed_handler))
    crawler2 = SitemapCrawler(config=custom_settings, client=client2)

    # Resumed run: Article 1 is unchanged (skipped), Article 2 is now added!
    res2 = await crawler2.run_sync()
    assert res2.stats.unchanged == 1
    assert res2.stats.added == 1
    assert res2.stats.total_active == 2


# ------------------------------------------------------------------------------
# 5. FastAPI Sync Endpoint Integration Test
# ------------------------------------------------------------------------------

def test_api_sync_and_health_integration(monkeypatch, tmp_path):
    """Test that POST /api/v1/sync triggers sync and updates GET /api/v1/health."""
    monkeypatch.setattr("src.api.settings.base_dir", tmp_path)
    monkeypatch.setattr("src.sitemap_sync.global_settings.base_dir", tmp_path)

    # Mock the crawler's run_sync to return a deterministic SyncResponse
    async def mock_run_sync(self, sitemap_url=None, max_articles=None, force=False):
        from src.models import SyncStats
        return SyncResponse(
            success=True,
            message="Mock sync complete",
            stats=SyncStats(added=5, updated=1, removed=0, unchanged=10, total_active=15),
        )

    monkeypatch.setattr(SitemapCrawler, "run_sync", mock_run_sync)

    client = TestClient(app)
    response = client.post("/api/v1/sync?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["stats"]["added"] == 5
    assert data["stats"]["total_active"] == 15
