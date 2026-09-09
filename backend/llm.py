"""The one place an LLM provider is chosen and called.

Everything else imports `ask()` and gets back a validated Pydantic object.
To move from Gemini to GPT, change LLM_PROVIDER + LLM_MODEL in .env and set
the matching key - no other file changes, because LangChain gives both
providers the same interface.
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter
from pydantic import BaseModel

from .config import get_settings

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
T = TypeVar("T", bound=BaseModel)

# How many times the provider SDK retries a transient failure before we
# give up. Kept low so an exhausted quota surfaces as an error the
# recruiter can act on instead of a request that hangs for minutes.
MAX_RETRIES = 2



@lru_cache
def get_model() -> BaseChatModel:
    s = get_settings()
    if not s.api_key:
        raise RuntimeError(
            f"No API key set for LLM_PROVIDER={s.LLM_PROVIDER}. "
            f"Add {'GOOGLE_API_KEY' if s.LLM_PROVIDER == 'gemini' else 'OPENAI_API_KEY'} to your .env file."
        )

    # Paces every call, including those the screening threads make in
    # parallel, so a bulk upload spreads out instead of tripping a 429.
    limiter = InMemoryRateLimiter(
        requests_per_second=s.LLM_RPM_CAP / 60,
        check_every_n_seconds=0.5,
        max_bucket_size=1,
    )

    if s.LLM_PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=s.LLM_MODEL,
            google_api_key=s.api_key,
            temperature=s.LLM_TEMPERATURE,
            rate_limiter=limiter,
            max_retries=MAX_RETRIES,
        )

    if s.LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=s.LLM_MODEL,
            api_key=s.api_key,
            temperature=s.LLM_TEMPERATURE,
            rate_limiter=limiter,
            max_retries=MAX_RETRIES,
        )

    raise ValueError(f"Unknown LLM_PROVIDER '{s.LLM_PROVIDER}'. Use 'gemini' or 'openai'.")


def load_prompt(name: str, **values: str) -> str:
    """Read `prompts/{name}.md` and substitute every {{placeholder}}."""
    text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def ask(prompt: str, schema: type[T]) -> T:
    """Send `prompt` to the configured model and return a validated `schema`.

    There is no retry wrapper here on purpose. Both provider SDKs already
    retry transient errors internally (bounded by MAX_RETRIES below), and
    stacking a second layer on top multiplied the wait rather than shortening
    it - an exhausted daily quota once took minutes to surface as an error.
    A call that still fails marks the row FAILED with the reason, and the UI
    offers a Retry button.
    """
    logger.info("LLM call -> %s", schema.__name__)
    return get_model().with_structured_output(schema).invoke(prompt)
