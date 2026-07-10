from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Zoom Agentic AI"
    app_version: str = "0.1.0"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_log_level: str = "INFO"

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/zoom_agentic_ai"
    )

    transcript_storage_dir: Path = Path("transcripts")
    log_dir: Path = Path("logs")

    zoom_account_id: str | None = None
    zoom_client_id: str | None = None
    zoom_client_secret: str | None = None
    zoom_webhook_secret_token: str | None = None
    zoom_token_url: str = "https://zoom.us/oauth/token"
    zoom_api_base_url: str = "https://api.zoom.us/v2"
    zoom_webhook_verify_signature: bool = True
    zoom_webhook_tolerance_seconds: int = 300
    zoom_oauth_timeout_seconds: float = 10.0
    zoom_oauth_retry_attempts: int = 3
    zoom_oauth_retry_backoff_seconds: float = 1.0

    ollama_base_url: str = "http://localhost:11434"
    ollama_primary_model: str = "qwen3:8b"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_embedding_dim: int = 768
    ollama_fallback_model: str = "llama3:8b"
    ollama_connect_timeout_seconds: float = 10.0
    ollama_read_timeout_seconds: float = 300.0
    ollama_retry_attempts: int = 3
    ollama_retry_backoff_seconds: float = 2.0

    atlas_max_history_turns: int = 6
    atlas_max_total_context_tokens: int = 6000
    atlas_max_retrieved_chunks: int = 5

    question_min_count: int = 10
    question_max_count: int = 20
    max_chunk_tokens: int = 4096
    dedup_similarity_threshold: float = 0.85
    workflow_max_retries: int = 1

    output_flashcards_per_chunk: int = 5
    output_short_questions_per_chunk: int = 3
    synthesize_max_input_tokens: int = 12000
    synthesize_max_output_tokens: int = 2000

    job_queue_num_workers: int = 2
    job_queue_poll_interval_seconds: float = 5.0
    job_queue_max_retries: int = 3
    job_queue_retry_backoff_base_seconds: float = 2.0
    job_queue_retry_backoff_max_seconds: float = 300.0
    job_queue_max_concurrent_runs: int = 4

    sync_scheduler_enabled: bool = True
    sync_scheduler_poll_interval_seconds: float = 60.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
