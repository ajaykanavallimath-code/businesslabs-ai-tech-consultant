"""Configuration management for the Knowledge Brain service."""

from pathlib import Path
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # --------------------------------------------------------------------------
    # Central LLM Settings (Claude)
    # --------------------------------------------------------------------------
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key for Claude",
    )
    claude_model_primary: str = Field(
        default="claude-3-5-sonnet-20241022",
        description="Primary model for complex reasoning, synthesis, and scoping",
    )
    claude_model_fast: str = Field(
        default="claude-3-haiku-20240307",
        description="Fast model for categorization, lightweight checks, and evaluation comparison",
    )
    mock_llm: bool = Field(
        default=False,
        description="If True, return mock LLM responses for offline unit tests without API calls",
    )

    # --------------------------------------------------------------------------
    # Knowledge Brain REST API Server
    # --------------------------------------------------------------------------
    kb_api_host: str = Field(
        default="127.0.0.1",
        description="Host interface to bind the API server",
    )
    kb_api_port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Port for the API server (1-65535)",
    )
    kb_api_url: str = Field(
        default="http://127.0.0.1:8000",
        description="Base URL exposed for Tasks 2 and 3 client communication",
    )

    # --------------------------------------------------------------------------
    # Storage & Directory Paths (Configurable with fallbacks)
    # --------------------------------------------------------------------------
    base_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent,
        description="Root directory for the knowledge-brain service",
    )
    kb_data_dir: Optional[Path] = Field(
        default=None,
        description="Optional custom path for persistent data directory",
    )
    chroma_persist_path: Optional[Path] = Field(
        default=None,
        description="Optional custom path for ChromaDB vector embeddings",
    )

    # --------------------------------------------------------------------------
    # Document Chunking & Vector Store Settings
    # --------------------------------------------------------------------------
    embedding_provider: str = Field(
        default="default",
        description="Embedding provider: 'default' (Chroma ONNX), 'sentence_transformers', or 'mock'",
    )
    embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        description="Model identifier for embeddings",
    )
    chunk_size: int = Field(
        default=800,
        ge=100,
        le=4000,
        description="Target character size per chunk",
    )
    chunk_overlap: int = Field(
        default=150,
        ge=0,
        le=1000,
        description="Character overlap between consecutive chunks",
    )
    chroma_collection_name: str = Field(
        default="bd_solution_center",
        description="ChromaDB collection name for articles",
    )

    # --------------------------------------------------------------------------
    # Sitemap Crawler & Ingestion Settings
    # --------------------------------------------------------------------------
    sitemap_url: str = Field(
        default="https://support.brilliantdirectories.com/support/sitemap.xml",
        description="URL of the Brilliant Directories Solution Center sitemap",
    )
    crawl_max_articles: int = Field(
        default=0,
        ge=0,
        description="Maximum articles to crawl (0 = unlimited / crawl all)",
    )
    crawl_request_timeout: float = Field(
        default=15.0,
        gt=0.0,
        le=120.0,
        description="HTTP request timeout in seconds per article page",
    )
    crawl_concurrency: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Concurrent HTTP requests allowed during crawling",
    )

    # --------------------------------------------------------------------------
    # Retrieval & Escalation Thresholds
    # --------------------------------------------------------------------------
    similarity_threshold: float = Field(
        default=0.60,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity required before escalating (0.0 to 1.0)",
    )
    confidence_threshold: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score required before flagging for human review (0.0 to 1.0)",
    )

    # --------------------------------------------------------------------------
    # Article Images & Screenshots
    # --------------------------------------------------------------------------
    max_images_per_answer: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Maximum number of relevant UI screenshots attached to an answer",
    )
    image_domains_whitelist: List[str] = Field(
        default_factory=lambda: [
            "support.brilliantdirectories.com",
            "s3.amazonaws.com",
            "cdn.freshdesk.com",
        ],
        description="Allowed trusted hostnames for article screenshots",
    )

    # --------------------------------------------------------------------------
    # Human Escalation & Auto-Learning
    # --------------------------------------------------------------------------
    auto_index_resolved_escalations: bool = Field(
        default=True,
        description="Automatically index resolved expert Q&A back into vector storage",
    )

    # --------------------------------------------------------------------------
    # Logging
    # --------------------------------------------------------------------------
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    # --------------------------------------------------------------------------
    # Validators
    # --------------------------------------------------------------------------
    @field_validator("sitemap_url")
    @classmethod
    def validate_sitemap_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError(f"Sitemap URL must start with 'http://' or 'https://': got '{v}'")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper_v = v.upper()
        if upper_v not in allowed:
            raise ValueError(f"Invalid log_level '{v}'. Allowed: {sorted(allowed)}")
        return upper_v

    # --------------------------------------------------------------------------
    # Path Properties (Dynamic resolution with override support)
    # --------------------------------------------------------------------------
    @property
    def data_dir(self) -> Path:
        """Resolved data directory (custom override if set, else base_dir/data)."""
        return self.kb_data_dir if self.kb_data_dir is not None else self.base_dir / "data"

    @property
    def chroma_persist_dir(self) -> Path:
        """Resolved ChromaDB vector path (custom override if set, else data_dir/chroma_db)."""
        return self.chroma_persist_path if self.chroma_persist_path is not None else self.data_dir / "chroma_db"

    @property
    def raw_articles_dir(self) -> Path:
        """Directory for cached crawled HTML and metadata."""
        return self.data_dir / "raw_articles"

    @property
    def sitemap_state_file(self) -> Path:
        """File tracking crawl status and lastmod dates for incremental sync."""
        return self.data_dir / "sitemap_state.json"

    @property
    def escalations_file(self) -> Path:
        """File storing pending and resolved human escalations."""
        return self.data_dir / "escalations.json"

    def ensure_directories(self) -> None:
        """Ensure all required data directories exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
        self.raw_articles_dir.mkdir(parents=True, exist_ok=True)

    model_config = SettingsConfigDict(
        env_file=[
            Path(__file__).resolve().parent.parent.parent / ".env",
            Path(__file__).resolve().parent.parent / ".env",
            ".env",
        ],
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Global singleton instance for settings
settings = Settings()
