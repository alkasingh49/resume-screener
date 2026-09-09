"""OpenAI adapter - a stub that proves the provider abstraction works.

Not used by default (LLM_PROVIDER=gemini). Switch to it by setting
LLM_PROVIDER=openai, LLM_MODEL=<an OpenAI chat model>, OPENAI_API_KEY in
.env - nothing else in the app changes.
"""

from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from backend.core.config import Settings


def _rate_limiter(settings: Settings) -> InMemoryRateLimiter:
    return InMemoryRateLimiter(
        requests_per_second=settings.LLM_RPM_CAP / 60,
        check_every_n_seconds=0.1,
        max_bucket_size=1,
    )


def build_chat_model(settings: Settings) -> ChatOpenAI:
    return ChatOpenAI(
        model_name=settings.LLM_MODEL,
        openai_api_key=settings.OPENAI_API_KEY,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        rate_limiter=_rate_limiter(settings),
    )


def build_embeddings(settings: Settings) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(model=settings.EMBEDDING_MODEL, openai_api_key=settings.OPENAI_API_KEY)
