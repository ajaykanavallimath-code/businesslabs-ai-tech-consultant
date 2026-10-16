"""Data models and API schemas for Knowledge Brain."""

from __future__ import annotations
from enum import Enum
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl


class EscalationStatus(str, Enum):
    """Lifecycle statuses for human escalation tasks."""
    PENDING = "pending"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ArticleStatus(str, Enum):
    """Lifecycle status for ingested articles."""
    ACTIVE = "active"
    REMOVED = "removed"


class ImageCitation(BaseModel):
    """Screenshot or UI graphic extracted from the article."""
    url: str = Field(..., description="Direct image URL")
    caption: Optional[str] = Field(default=None, description="Image caption or alt text")
    context: Optional[str] = Field(
        default=None,
        description="Associated instructional step or UI guidance context"
    )


class SitemapEntry(BaseModel):
    """Parsed entry from Brilliant Directories sitemap XML."""
    url: str = Field(..., description="Canonical page URL")
    lastmod: Optional[str] = Field(default=None, description="ISO format last modified date")
    changefreq: Optional[str] = Field(default=None, description="Change frequency directive")
    priority: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Sitemap priority")


class ArticleRecord(BaseModel):
    """Persistent record of an ingested knowledge article."""
    url: str = Field(..., description="Canonical URL of the article")
    title: str = Field(..., description="Article title")
    category: Optional[str] = Field(default=None, description="Category name from breadcrumb")
    folder: Optional[str] = Field(default=None, description="Folder or topic name")
    content: str = Field(..., description="Cleaned article textual content")
    images: List[ImageCitation] = Field(default_factory=list, description="Instructional screenshots")
    lastmod: Optional[str] = Field(default=None, description="Lastmod timestamp from sitemap")
    content_hash: str = Field(..., description="SHA-256 hash of title and cleaned content")
    raw_html_path: Optional[str] = Field(default=None, description="Local path to cached raw HTML file")
    status: ArticleStatus = Field(default=ArticleStatus.ACTIVE, description="Active or soft-removed")
    first_crawled_at: datetime = Field(default_factory=datetime.utcnow)
    last_crawled_at: datetime = Field(default_factory=datetime.utcnow)
    removed_at: Optional[datetime] = None


class DocumentChunk(BaseModel):
    """Searchable text chunk of an article with attached metadata and screenshots."""
    chunk_id: str = Field(..., description="Unique chunk identifier, e.g. {article_id}_c{index}")
    article_id: str = Field(..., description="ID of the parent article, e.g. 12000065940")
    url: str = Field(..., description="Canonical source URL")
    title: str = Field(..., description="Article title")
    category: Optional[str] = Field(default=None, description="Category name from breadcrumb")
    folder: Optional[str] = Field(default=None, description="Folder or topic name")
    section: Optional[str] = Field(default=None, description="Section heading context")
    content: str = Field(..., description="Cleaned chunk text")
    chunk_index: int = Field(default=0, ge=0, description="Sequential index within article")
    total_chunks: int = Field(default=1, ge=1, description="Total chunks for this article")
    images: List[ImageCitation] = Field(default_factory=list, description="Associated screenshots")


class SourceCitation(BaseModel):
    """Citation pointing to a specific Brilliant Directories knowledge article."""
    title: str = Field(..., description="Title of the source article")
    url: str = Field(..., description="Canonical URL of the article")
    section: Optional[str] = Field(default=None, description="Section heading or step context")
    snippet: str = Field(..., description="Relevant text excerpt supporting the answer")
    score: float = Field(..., ge=0.0, le=1.0, description="Relevance similarity score")
    images: List[ImageCitation] = Field(default_factory=list, description="Relevant screenshots attached to cited excerpt")



class QueryRequest(BaseModel):
    """Incoming search/question query."""
    query: str = Field(..., min_length=2, description="The user or agent inquiry")
    top_k: int = Field(default=3, ge=1, le=10, description="Number of source chunks to retrieve")
    min_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional custom similarity threshold"
    )


class QueryResponse(BaseModel):
    """Standardized response containing answer, citations, images, or escalation flag."""
    query: str
    answer: str = Field(..., description="Claude synthesized answer or escalation statement")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence estimate")
    escalated: bool = Field(
        default=False,
        description="True if query could not be verified by retrieved context"
    )
    escalation_id: Optional[str] = Field(
        default=None,
        description="Task ID if escalated to human expert"
    )
    sources: List[SourceCitation] = Field(
        default_factory=list,
        description="List of cited articles and snippets"
    )
    images: List[ImageCitation] = Field(
        default_factory=list,
        description="Relevant UI screenshots illustrating the steps"
    )


class CapabilityCheckRequest(BaseModel):
    """Used by Task 3 (Meeting-to-Scope) to check if a requirement is a native BD setting."""
    requirement: str = Field(
        ...,
        min_length=3,
        description="Extracted client feature requirement"
    )


class CapabilityCheckResponse(BaseModel):
    """Response verifying whether a requirement can be met with native settings or custom code."""
    requirement: str
    supported_natively: bool = Field(
        ...,
        description="True if feature exists natively in Brilliant Directories"
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    matching_feature: Optional[str] = Field(
        default=None,
        description="Name of the native feature or add-on"
    )
    configuration_path: Optional[str] = Field(
        default=None,
        description="Admin dashboard navigation path (e.g. Settings > Membership Plans)"
    )
    documentation_urls: List[str] = Field(
        default_factory=list,
        description="Supporting documentation links"
    )
    notes: str = Field(
        ...,
        description="Consultant guidance on configuration vs custom development"
    )


class EscalationTask(BaseModel):
    """An escalation task queued for human expert review."""
    id: str = Field(..., description="Unique escalation identifier")
    query: str = Field(..., description="The query that could not be confidently answered")
    reason: str = Field(..., description="Why the answer was not confident or missing")
    retrieved_sources: List[SourceCitation] = Field(default_factory=list)
    status: EscalationStatus = Field(default=EscalationStatus.PENDING)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    resolution: Optional[str] = Field(
        default=None,
        description="Human expert verified response"
    )
    expert_name: Optional[str] = None


class EscalationResolveRequest(BaseModel):
    """Expert response to resolve an escalation and trigger knowledge base learning."""
    resolution: str = Field(
        ...,
        min_length=5,
        description="The verified ground truth answer provided by human expert"
    )
    expert_name: str = Field(
        default="AI Tech Consultant",
        description="Name or ID of reviewing consultant"
    )


class SyncStats(BaseModel):
    """Statistics for incremental sitemap synchronization."""
    added: int = Field(default=0, description="New articles indexed")
    updated: int = Field(default=0, description="Existing articles refreshed")
    removed: int = Field(default=0, description="Obsolete articles deleted")
    unchanged: int = Field(default=0, description="Articles skipped because lastmod is identical")
    total_active: int = Field(default=0, description="Total active articles in index")


class SyncResponse(BaseModel):
    """Result of an incremental sitemap sync operation."""
    success: bool = True
    message: str
    stats: SyncStats
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HealthResponse(BaseModel):
    """Health status and index metrics."""
    status: str = "healthy"
    version: str = "0.1.0"
    service: str = "Knowledge Brain"
    total_articles: int = 0
    total_chunks: int = 0
    last_sync: Optional[datetime] = None
