"""Google Gemini adapter.

This file (and openai.py) are the ONLY places in `backend/` allowed to import
a provider SDK - `make check-provider-isolation` enforces that.
"""

from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from backend.core.config import Settings


def _rate_limiter(settings: Settings) -> InMemoryRateLimiter:
    """Shared by chat and (if ever needed) embeddings - RPM cap from config."""
    return InMemoryRateLimiter(
        requests_per_second=settings.LLM_RPM_CAP / 60,
        check_every_n_seconds=0.1,
        max_bucket_size=1,
    )


def build_chat_model(settings: Settings) -> ChatGoogleGenerativeAI:
    """Build the Gemini chat model. Rate limiting is attached here so it
    applies to every call path, including native tool-calling / structured
    output, not just plain `.invoke()`.
    """
    return ChatGoogleGenerativeAI(
        model=settings.LLM_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=settings.LLM_TEMPERATURE,
        max_output_tokens=settings.LLM_MAX_TOKENS,
        rate_limiter=_rate_limiter(settings),
    )


def build_embeddings(settings: Settings) -> GoogleGenerativeAIEmbeddings:
    """Build the Gemini embeddings model. Gemini expects a 'models/' prefix."""
    model_name = settings.EMBEDDING_MODEL
    if not model_name.startswith("models/"):
        model_name = f"models/{model_name}"
    return GoogleGenerativeAIEmbeddings(model=model_name, google_api_key=settings.GOOGLE_API_KEY)
