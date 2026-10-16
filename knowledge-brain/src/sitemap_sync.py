"""Sitemap parser and 3-way incremental crawler for Brilliant Directories Solution Center."""

import asyncio
import json
import logging
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import httpx

from src.config import Settings, settings as global_settings
from src.html_parser import extract_article
from src.models import (
    ArticleRecord,
    ArticleStatus,
    SitemapEntry,
    SyncResponse,
    SyncStats,
)

logger = logging.getLogger("knowledge_brain.sitemap_sync")


class SitemapParser:
    """Parses XML sitemaps and extracts valid Solution Center article entries."""

    @staticmethod
    def parse(xml_content: str) -> List[SitemapEntry]:
        """Parse sitemap XML content into a list of SitemapEntry objects.

        Handles XML namespaces, malformed XML, and URL deduplication.
        """
        if not xml_content or not xml_content.strip():
            return []

        entries: List[SitemapEntry] = []
        seen_urls: Set[str] = set()

        try:
            # Strip XML declaration if problematic
            clean_xml = re.sub(r"<\?xml[^>]+\?>", "", xml_content.strip()).strip()
            root = ET.fromstring(clean_xml)
        except ET.ParseError as e:
            logger.warning(f"Standard XML parsing failed ({e}). Attempting regex recovery...")
            return SitemapParser._parse_with_regex(xml_content)

        # Handle sitemap namespace
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        url_elements = root.findall(".//sm:url", ns) or root.findall(".//url")

        for url_el in url_elements:
            loc_el = url_el.find("sm:loc", ns) if ns else None
            if loc_el is None:
                loc_el = url_el.find("loc")

            if loc_el is None or not loc_el.text:
                continue

            raw_url = loc_el.text.strip()
            if not SitemapParser._is_valid_solution_url(raw_url):
                continue

            if raw_url in seen_urls:
                continue
            seen_urls.add(raw_url)

            # Lastmod
            lastmod_el = url_el.find("sm:lastmod", ns) if ns else None
            if lastmod_el is None:
                lastmod_el = url_el.find("lastmod")
            lastmod = lastmod_el.text.strip() if (lastmod_el is not None and lastmod_el.text) else None

            # Changefreq
            cf_el = url_el.find("sm:changefreq", ns) if ns else None
            if cf_el is None:
                cf_el = url_el.find("changefreq")
            changefreq = cf_el.text.strip() if (cf_el is not None and cf_el.text) else None

            # Priority
            p_el = url_el.find("sm:priority", ns) if ns else None
            if p_el is None:
                p_el = url_el.find("priority")
            priority = None
            if p_el is not None and p_el.text:
                try:
                    priority = float(p_el.text.strip())
                except ValueError:
                    priority = None

            entries.append(
                SitemapEntry(
                    url=raw_url,
                    lastmod=lastmod,
                    changefreq=changefreq,
                    priority=priority,
                )
            )

        return entries

    @staticmethod
    def _parse_with_regex(xml_content: str) -> List[SitemapEntry]:
        """Regex fallback parser for severely malformed XML sitemaps."""
        entries: List[SitemapEntry] = []
        seen_urls: Set[str] = set()

        url_blocks = re.findall(r"<url>(.*?)</url>", xml_content, flags=re.DOTALL | re.IGNORECASE)
        for block in url_blocks:
            loc_match = re.search(r"<loc>(.*?)</loc>", block, flags=re.IGNORECASE)
            if not loc_match:
                continue

            url = loc_match.group(1).strip()
            if not SitemapParser._is_valid_solution_url(url) or url in seen_urls:
                continue
            seen_urls.add(url)

            lastmod_match = re.search(r"<lastmod>(.*?)</lastmod>", block, flags=re.IGNORECASE)
            lastmod = lastmod_match.group(1).strip() if lastmod_match else None

            entries.append(SitemapEntry(url=url, lastmod=lastmod))

        return entries

    @staticmethod
    def _is_valid_solution_url(url: str) -> bool:
        """Filter out non-article URLs like login, search, or tickets."""
        if not (url.startswith("http://") or url.startswith("https://")):
            return False

        parsed = urlparse(url)
        path = parsed.path.lower()

        # Reject utility and authentication routes
        disallowed = ["/support/search", "/support/tickets", "/support/login", "/support/signup"]
        if any(d in path for d in disallowed):
            return False

        return True


class SitemapCrawler:
    """Manages incremental sitemap crawling, change detection, and persistence."""

    def __init__(
        self,
        config: Optional[Settings] = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.config = config or global_settings
        self._external_client = client
        self.state: Dict[str, ArticleRecord] = {}
        self._load_state()

    def _load_state(self) -> None:
        """Load stored article records from sitemap_state_file."""
        state_file = self.config.sitemap_state_file
        if not state_file.exists():
            self.state = {}
            return

        try:
            with open(state_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            self.state = {
                url: ArticleRecord.model_validate(record_dict)
                for url, record_dict in raw_data.items()
            }
            logger.info(f"Loaded {len(self.state)} article records from {state_file}")
        except Exception as e:
            logger.error(f"Failed to load sitemap state from {state_file}: {e}")
            self.state = {}

    def _save_state(self) -> None:
        """Atomically persist state to sitemap_state_file."""
        state_file = self.config.sitemap_state_file
        state_file.parent.mkdir(parents=True, exist_ok=True)

        data = {url: record.model_dump(mode="json") for url, record in self.state.items()}

        # Atomic write via temporary file
        temp_dir = state_file.parent
        with tempfile.NamedTemporaryFile("w", dir=temp_dir, delete=False, encoding="utf-8") as tf:
            json.dump(data, tf, indent=2)
            temp_name = tf.name

        Path(temp_name).replace(state_file)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._external_client is not None:
            return self._external_client
        return httpx.AsyncClient(
            headers={"User-Agent": "BusinessLabs-AITechConsultant/1.0"},
            timeout=httpx.Timeout(self.config.crawl_request_timeout),
            follow_redirects=True,
        )

    async def fetch_sitemap(self, sitemap_url: Optional[str] = None) -> List[SitemapEntry]:
        """Fetch and parse the XML sitemap."""
        url = sitemap_url or self.config.sitemap_url
        client = await self._get_client()
        should_close = self._external_client is None

        try:
            logger.info(f"Fetching sitemap from: {url}")
            response = await client.get(url)
            response.raise_for_status()
            return SitemapParser.parse(response.text)
        except Exception as e:
            logger.error(f"Error fetching sitemap from {url}: {e}")
            raise
        finally:
            if should_close:
                await client.aclose()

    async def crawl_single_article(
        self,
        url: str,
        lastmod: Optional[str] = None,
        max_retries: int = 3,
    ) -> Optional[ArticleRecord]:
        """Fetch an individual article with retries, parse it, and return ArticleRecord."""
        client = await self._get_client()
        should_close = self._external_client is None

        for attempt in range(1, max_retries + 1):
            try:
                response = await client.get(url)
                if response.status_code == 404:
                    logger.warning(f"Article not found (404): {url}")
                    return None
                response.raise_for_status()

                html_content = response.text
                parsed = extract_article(
                    html=html_content,
                    source_url=url,
                    image_whitelist=self.config.image_domains_whitelist,
                    max_images=self.config.max_images_per_answer,
                )

                # Persist raw HTML for auditability and offline re-parsing
                raw_filename = f"{parsed.content_hash[:16]}.html"
                raw_path = self.config.raw_articles_dir / raw_filename
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text(html_content, encoding="utf-8")

                now = datetime.utcnow()
                existing = self.state.get(url)
                first_crawled = existing.first_crawled_at if existing else now

                return ArticleRecord(
                    url=url,
                    title=parsed.title,
                    category=parsed.category,
                    folder=parsed.folder,
                    content=parsed.content,
                    images=parsed.images,
                    lastmod=lastmod,
                    content_hash=parsed.content_hash,
                    raw_html_path=str(raw_path),
                    status=ArticleStatus.ACTIVE,
                    first_crawled_at=first_crawled,
                    last_crawled_at=now,
                )
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                logger.warning(f"Attempt {attempt}/{max_retries} failed for {url}: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(0.5 * attempt)
                else:
                    logger.error(f"All {max_retries} attempts failed for {url}")
                    return None
            finally:
                if should_close and attempt == max_retries:
                    await client.aclose()

        return None

    async def run_sync(
        self,
        sitemap_url: Optional[str] = None,
        max_articles: Optional[int] = None,
        force: bool = False,
    ) -> SyncResponse:
        """Execute 3-way incremental synchronization (Added, Updated, Removed, Unchanged).

        Args:
            sitemap_url: Override sitemap URL.
            max_articles: Max articles to process (useful for tests/quick sync).
            force: If True, re-crawls articles even if lastmod is unchanged.

        Returns:
            SyncResponse containing execution statistics.
        """
        self.config.ensure_directories()
        entries = await self.fetch_sitemap(sitemap_url)

        if max_articles is not None and max_articles > 0:
            entries = entries[:max_articles]
        elif self.config.crawl_max_articles > 0:
            entries = entries[: self.config.crawl_max_articles]

        sitemap_map = {entry.url: entry for entry in entries}
        current_urls = set(sitemap_map.keys())
        stored_urls = set(self.state.keys())

        # 1. Identify Removed Articles (Safe Soft-Removal)
        removed_count = 0
        for url, record in self.state.items():
            if record.status == ArticleStatus.ACTIVE and url not in current_urls:
                record.status = ArticleStatus.REMOVED
                record.removed_at = datetime.utcnow()
                removed_count += 1
                logger.info(f"Marked article as removed: {url}")

        # 2. Identify Added, Updated, and Unchanged Articles
        to_fetch: List[Tuple[str, Optional[str], str]] = []  # (url, lastmod, action_type)
        unchanged_count = 0

        for url, entry in sitemap_map.items():
            existing = self.state.get(url)

            if existing is None or existing.status == ArticleStatus.REMOVED:
                # Added (new or revived)
                to_fetch.append((url, entry.lastmod, "added"))
            elif force or existing.lastmod != entry.lastmod:
                # Updated lastmod
                to_fetch.append((url, entry.lastmod, "updated"))
            else:
                # Unchanged: lastmod matches
                unchanged_count += 1

        logger.info(
            f"Sitemap delta analysis: {len(to_fetch)} to fetch, "
            f"{unchanged_count} unchanged, {removed_count} removed"
        )

        # 3. Concurrently Fetch and Ingest with Semaphore
        sem = asyncio.Semaphore(self.config.crawl_concurrency)
        added_count = 0
        updated_count = 0

        async def _fetch_worker(url: str, lastmod: Optional[str], action: str):
            nonlocal added_count, updated_count
            async with sem:
                record = await self.crawl_single_article(url, lastmod)
                if record:
                    self.state[url] = record
                    if action == "added":
                        added_count += 1
                    else:
                        updated_count += 1
                    # Resumable save after each record
                    self._save_state()

        if to_fetch:
            tasks = [_fetch_worker(u, lm, act) for u, lm, act in to_fetch]
            await asyncio.gather(*tasks)

        # Final state save
        self._save_state()

        total_active = sum(1 for r in self.state.values() if r.status == ArticleStatus.ACTIVE)

        stats = SyncStats(
            added=added_count,
            updated=updated_count,
            removed=removed_count,
            unchanged=unchanged_count,
            total_active=total_active,
        )

        message = (
            f"Sitemap sync completed. Added: {added_count}, Updated: {updated_count}, "
            f"Removed: {removed_count}, Unchanged: {unchanged_count}. "
            f"Total active articles: {total_active}."
        )
        logger.info(message)

        return SyncResponse(
            success=True,
            message=message,
            stats=stats,
        )
