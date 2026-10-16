"""Semantic text chunker for Brilliant Directories knowledge articles."""

import re
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from src.models import ArticleRecord, DocumentChunk, ImageCitation


def extract_article_id(url: str) -> str:
    """Extract numeric or slug ID from a Brilliant Directories URL."""
    # Matches /articles/12000065940-... or /solutions/12000001358
    match = re.search(r"/(?:articles|solutions|folders)/(\d+)", url)
    if match:
        return match.group(1)

    # Fallback to sanitized path segment
    path = urlparse(url).path.strip("/").replace("/", "_")
    return path if path else "doc"


def _is_heading(line: str) -> bool:
    """Check if a line represents a section heading or instructional step."""
    line_clean = line.strip()
    if not line_clean:
        return False
    # Markdown heading (## Heading)
    if re.match(r"^#{1,4}\s+.+", line_clean):
        return True
    # Step markers: Step 1:, Step 2.
    if re.match(r"^Step\s*\d+[:.]\s*", line_clean, flags=re.IGNORECASE):
        return True
    # Short titled lines ending in colon (e.g. "Connection Choices:", "Important:")
    if line_clean.endswith(":") and len(line_clean) < 60:
        return True
    # Guide / Section marker
    if re.match(r"^(?:Section|Guide\s*\d+[:.]|Overview|Introduction)\b", line_clean, flags=re.IGNORECASE):
        return True
    return False


def chunk_article(
    article: ArticleRecord,
    chunk_size: int = 800,
    chunk_overlap: int = 150,
) -> List[DocumentChunk]:
    """Split an ArticleRecord into semantically meaningful chunks with metadata and screenshots.

    Args:
        article: The ingested ArticleRecord.
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Overlap characters between adjacent chunks.

    Returns:
        List of DocumentChunk instances.
    """
    raw_content = (article.content or "").strip()
    if not raw_content:
        return []

    article_id = extract_article_id(article.url)

    # If article is very short, emit a single chunk
    if len(raw_content) <= chunk_size:
        return [
            DocumentChunk(
                chunk_id=f"{article_id}_c0",
                article_id=article_id,
                url=article.url,
                title=article.title,
                category=article.category,
                folder=article.folder,
                section="Main Overview",
                content=raw_content,
                chunk_index=0,
                total_chunks=1,
                images=article.images,
            )
        ]

    # Split into paragraphs and recognize headings
    lines = raw_content.split("\n")
    paragraphs: List[Tuple[Optional[str], str]] = []  # (section_heading, text_block)
    current_section = "General Overview"
    current_para: List[str] = []

    for line in lines:
        line_str = line.strip()
        if not line_str:
            if current_para:
                paragraphs.append((current_section, " ".join(current_para)))
                current_para = []
            continue

        if _is_heading(line_str):
            if current_para:
                paragraphs.append((current_section, " ".join(current_para)))
                current_para = []
            # Update heading context
            current_section = re.sub(r"^#{1,4}\s*", "", line_str).strip(" :")
            current_para.append(line_str)
        else:
            current_para.append(line_str)

    if current_para:
        paragraphs.append((current_section, " ".join(current_para)))

    # Assemble paragraphs into chunks with sliding overlap
    chunks_raw: List[Tuple[str, str]] = []  # (section, text)
    curr_chunk_parts: List[str] = []
    curr_chunk_len = 0
    curr_section = paragraphs[0][0] if paragraphs else "Overview"

    for sec, para_text in paragraphs:
        para_len = len(para_text)

        # If adding this paragraph exceeds chunk_size and we already have content
        if curr_chunk_len + para_len > chunk_size and curr_chunk_parts:
            combined = "\n\n".join(curr_chunk_parts)
            chunks_raw.append((curr_section, combined))

            # Sliding window overlap: keep tail of current chunk
            overlap_prefix = ""
            if chunk_overlap > 0 and len(combined) > chunk_overlap:
                overlap_prefix = combined[-chunk_overlap:].strip()

            curr_chunk_parts = [overlap_prefix, para_text] if overlap_prefix else [para_text]
            curr_chunk_len = sum(len(p) for p in curr_chunk_parts)
            curr_section = sec
        else:
            curr_chunk_parts.append(para_text)
            curr_chunk_len += para_len
            curr_section = sec

    if curr_chunk_parts:
        chunks_raw.append((curr_section, "\n\n".join(curr_chunk_parts).strip()))

    # Build final DocumentChunk models and distribute relevant images
    total_chunks = len(chunks_raw)
    result_chunks: List[DocumentChunk] = []

    for idx, (section_title, chunk_text) in enumerate(chunks_raw):
        chunk_id = f"{article_id}_c{idx}"

        # Match relevant screenshots to this chunk
        chunk_images: List[ImageCitation] = []
        chunk_lower = chunk_text.lower()

        for img in article.images:
            caption_words = set(re.findall(r"\w{4,}", (img.caption or "").lower()))
            context_words = set(re.findall(r"\w{4,}", (img.context or "").lower()))
            target_words = caption_words | context_words

            # If image context matches chunk keywords, or if single image attached to first chunk
            if any(w in chunk_lower for w in target_words) or (idx == 0 and len(article.images) <= 2):
                if img not in chunk_images:
                    chunk_images.append(img)

        result_chunks.append(
            DocumentChunk(
                chunk_id=chunk_id,
                article_id=article_id,
                url=article.url,
                title=article.title,
                category=article.category,
                folder=article.folder,
                section=section_title,
                content=chunk_text,
                chunk_index=idx,
                total_chunks=total_chunks,
                images=chunk_images,
            )
        )

    return result_chunks
