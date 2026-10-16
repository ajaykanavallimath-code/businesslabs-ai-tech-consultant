"""HTML content and screenshot extractor for Brilliant Directories articles."""

import hashlib
import re
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, Tag

from src.models import ImageCitation


class ParsedArticleContent:
    """Structured data extracted from an article HTML page."""

    def __init__(
        self,
        title: str,
        content: str,
        canonical_url: str,
        category: Optional[str] = None,
        folder: Optional[str] = None,
        images: Optional[List[ImageCitation]] = None,
        content_hash: str = "",
    ):
        self.title = title
        self.content = content
        self.canonical_url = canonical_url
        self.category = category
        self.folder = folder
        self.images = images or []
        self.content_hash = content_hash or self.compute_hash(title, content)

    @staticmethod
    def compute_hash(title: str, content: str) -> str:
        """Compute SHA-256 hash over normalized title and content."""
        data = f"{title.strip()}\n{content.strip()}".encode("utf-8")
        return hashlib.sha256(data).hexdigest()


def extract_article(
    html: str,
    source_url: str,
    image_whitelist: Optional[List[str]] = None,
    max_images: int = 5,
) -> ParsedArticleContent:
    """Parse HTML and extract clean title, breadcrumbs, text, and screenshots.

    Args:
        html: Raw HTML content.
        source_url: The URL where this HTML was fetched from.
        image_whitelist: Allowed hostnames for article screenshots.
        max_images: Maximum number of images to attach.

    Returns:
        ParsedArticleContent object with title, content, breadcrumbs, images, and hash.
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1. Canonical URL
    canonical_tag = soup.find("link", rel="canonical")
    canonical_url = canonical_tag.get("href") if canonical_tag and canonical_tag.get("href") else source_url

    # 2. Extract Title
    title = ""
    title_el = (
        soup.find("h1", class_="post-title")
        or soup.find("h1")
        or soup.find("meta", property="og:title")
    )
    if title_el:
        if title_el.name == "meta":
            title = title_el.get("content", "").strip()
        else:
            title = title_el.get_text(strip=True)

    if not title and soup.title:
        title = soup.title.get_text(strip=True)

    # Clean typical title suffix
    title = re.sub(
        r"\s*\|\s*Brilliant Directories Documentation\s*\|\s*BD Support",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()
    if not title:
        title = "Untitled Brilliant Directories Guide"

    # 3. Extract Breadcrumbs (Category and Folder)
    category: Optional[str] = None
    folder: Optional[str] = None

    breadcrumb_container = soup.find("div", class_="breadcrumb") or soup.find("nav", class_="breadcrumb")
    if breadcrumb_container:
        links = [a.get_text(strip=True) for a in breadcrumb_container.find_all("a")]
        # Typical: [Solution home / Solution Center Home, Section: Category, Folder Name, Article Title]
        filtered_links = [
            l for l in links
            if l.lower() not in {"solution home", "solution center home", "home"}
        ]
        if filtered_links:
            cat_raw = filtered_links[0]
            category = re.sub(r"^Section:\s*", "", cat_raw).strip()
        if len(filtered_links) > 1:
            folder = filtered_links[1].strip()

    # 4. Locate Main Article Body Container
    article_container = (
        soup.find("article", class_="article-body")
        or soup.find(id="article-body")
        or soup.find("div", class_="bd-api-docs")
        or soup.find("section", class_="main content")
        or soup.find("article")
        or soup.body
        or soup
    )

    # 5. Extract Screenshots BEFORE decomposing elements
    images: List[ImageCitation] = []
    if article_container:
        for img in article_container.find_all("img"):
            if len(images) >= max_images:
                break

            src = img.get("src") or img.get("data-src")
            if not src:
                continue

            # Resolve relative URLs
            full_img_url = urljoin(source_url, src)
            parsed_img = urlparse(full_img_url)

            # Check domain whitelist if configured
            if image_whitelist:
                hostname = (parsed_img.hostname or "").lower()
                if not any(allowed.lower() in hostname for allowed in image_whitelist):
                    continue

            # Filter out tracking pixels, icons, or badges
            if any(term in full_img_url.lower() for term in ["1x1", "tracking", "logo", "fav_icon", "badge"]):
                continue

            # Extract caption and surrounding context
            caption = img.get("alt") or img.get("title") or ""
            caption = caption.strip() if caption else None

            # Look for context: nearest following <em> or preceding heading
            context = None
            parent_p = img.find_parent("p")
            if parent_p:
                next_p = parent_p.find_next_sibling("p")
                if next_p and next_p.find("em"):
                    context = next_p.get_text(strip=True)

            if not context:
                prev_heading = img.find_previous(["h2", "h3", "h4"])
                if prev_heading:
                    context = f"Step/Section: {prev_heading.get_text(strip=True)}"

            images.append(
                ImageCitation(
                    url=full_img_url,
                    caption=caption,
                    context=context,
                )
            )

    # 6. Decompose noise elements
    # We make a copy of the container to clean text
    content_soup = BeautifulSoup(str(article_container), "html.parser")
    for noise_sel in [
        ".article-footer-content",
        ".article-vote",
        "#voting-container",
        ".the-article-link",
        ".breadcrumb",
        ".bread-links",
        ".sidebar",
        ".banner",
        ".holiday-promos-banner",
        "script",
        "style",
        "nav",
        "form",
        ".copy-link-to-section",
        "header",
        "footer",
    ]:
        for el in content_soup.select(noise_sel):
            el.decompose()

    # Extract text and normalize whitespace
    raw_text = content_soup.get_text(separator="\n", strip=True)
    # Collapse 3+ newlines to 2
    cleaned_text = re.sub(r"\n{3,}", "\n\n", raw_text).strip()

    content_hash = ParsedArticleContent.compute_hash(title, cleaned_text)

    return ParsedArticleContent(
        title=title,
        content=cleaned_text,
        canonical_url=canonical_url,
        category=category,
        folder=folder,
        images=images,
        content_hash=content_hash,
    )
