"""Application configuration, loaded from environment variables / .env.

This is the single source of truth for settings. No module outside this file
should call `os.getenv` directly for anything listed here.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings, populated from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    APP_NAME: str = "AI Resume Screener"
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # --- API server ---
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # --- Storage ---
    DATABASE_URL: str = "sqlite:///./data/app.db"
    DATA_DIR: Path = Path("data")
    UPLOAD_DIR_JDS: Path = Path("data/uploads/jds")
    UPLOAD_DIR_RESUMES: Path = Path("data/uploads/resumes")
    CHROMA_DIR: Path = Path("data/chroma")

    # --- LLM provider selection (see backend/llm/factory.py) ---
    LLM_PROVIDER: str = "gemini"
    LLM_MODEL: str = "gemini-2.5-flash"
    EMBEDDING_PROVIDER: str = "gemini"
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_TOKENS: int = 2048
    LLM_RPM_CAP: int = 8

    # --- Provider API keys ---
    GOOGLE_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None

    # --- Scoring thresholds (config-driven, never hardcoded in prompts) ---
    FIT_THRESHOLD_BEST: int = 75
    FIT_THRESHOLD_MEDIUM: int = 45

    # --- Background pipeline (services/pipeline.py) ---
    PIPELINE_MAX_WORKERS: int = 3  # bounded concurrency for parse+score across a batch

    # --- CORS ---
    CORS_ORIGINS: str = "*"

    def ensure_data_dirs(self) -> None:
        """Create the on-disk directories this app writes to, if missing."""
        for directory in (
            self.DATA_DIR,
            self.UPLOAD_DIR_JDS,
            self.UPLOAD_DIR_RESUMES,
            self.CHROMA_DIR,
        ):
            Path(directory).mkdir(parents=True, exist_ok=True)

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS_ORIGINS as a list, splitting the comma-separated env value."""
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings instance (env is read once per process)."""
    return Settings()
