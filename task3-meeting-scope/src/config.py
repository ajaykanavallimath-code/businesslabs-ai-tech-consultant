"""
Configuration management for Task 3: Meeting to Scope.
Loads settings from environment variables and root .env file.
"""

import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load from project root .env first
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env")
load_dotenv()


class Task3Settings(BaseSettings):
    """Settings for Meeting to Scope agent pipeline."""
    # Knowledge Brain API Integration
    kb_api_url: str = os.getenv("KB_API_URL", "http://127.0.0.1:8000")
    kb_timeout_seconds: float = float(os.getenv("KB_TIMEOUT_SECONDS", "8.0"))
    mock_kb: bool = os.getenv("MOCK_KB", "true").lower() in ("true", "1")

    # Central LLM (Claude)
    anthropic_api_key: Optional[str] = os.getenv("ANTHROPIC_API_KEY", None)
    claude_model_primary: str = os.getenv("CLAUDE_MODEL_PRIMARY", "claude-3-5-sonnet-20241022")
    claude_model_fast: str = os.getenv("CLAUDE_MODEL_FAST", "claude-3-haiku-20240307")
    mock_llm: bool = os.getenv("MOCK_LLM", "true").lower() in ("true", "1") or not os.getenv("ANTHROPIC_API_KEY")

    # Task 3 API & Server
    task3_api_host: str = os.getenv("TASK3_API_HOST", "127.0.0.1")
    task3_api_port: int = int(os.getenv("TASK3_API_PORT", "8001"))

    # Persistence
    task3_data_dir: str = os.getenv(
        "TASK3_DATA_DIR",
        str(Path(__file__).resolve().parent.parent / "data")
    )

    # Delivery Safety Gate
    enable_client_delivery: bool = os.getenv("ENABLE_CLIENT_DELIVERY", "false").lower() in ("true", "1")

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


settings = Task3Settings()
