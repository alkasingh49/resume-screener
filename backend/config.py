"""Application settings, read once from environment / .env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "AI Resume Screener"

    DATABASE_URL: str = "sqlite:///./data/app.db"
    UPLOAD_DIR: Path = Path("data/uploads")

    # Swap the LLM by changing these + the matching key below. Nothing else
    # in the app knows which provider is in use.
    LLM_PROVIDER: str = "gemini"  # "gemini" | "openai"
    LLM_MODEL: str = "gemini-3.1-flash-lite"
    LLM_TEMPERATURE: float = 0.1
    GOOGLE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # Overall score (0-100) cutoffs for the Fit label.
    FIT_BEST_MIN: int = 75
    FIT_MEDIUM_MIN: int = 45

    # How many resumes to screen at once during a bulk upload.
    MAX_PARALLEL_RESUMES: int = 4

    # Requests per minute allowed to the provider. The Gemini free tier is
    # 5 RPM, so we pace calls to that rather than bursting into a 429 and
    # then waiting out an exponential backoff. Raise it on a paid plan.
    LLM_RPM_CAP: int = 5

    # Vite dev server. Comma-separated; "*" allows everything.
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def api_key(self) -> str:
        return self.GOOGLE_API_KEY if self.LLM_PROVIDER == "gemini" else self.OPENAI_API_KEY

    @property
    def cors_list(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
