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
from pydantic import BaseModel
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from .config import get_settings

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
T = TypeVar("T", bound=BaseModel)

# Free-tier Gemini rate-limits readily, so retry those but fail fast on a
# genuinely bad request that would just fail again identically.
_TRANSIENT = ("429", "rate limit", "quota", "timeout", "unavailable", "503", "internal error")


@lru_cache
def get_model() -> BaseChatModel:
    s = get_settings()
    if not s.api_key:
        raise RuntimeError(
            f"No API key set for LLM_PROVIDER={s.LLM_PROVIDER}. "
            f"Add {'GOOGLE_API_KEY' if s.LLM_PROVIDER == 'gemini' else 'OPENAI_API_KEY'} to your .env file."
        )

    if s.LLM_PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=s.LLM_MODEL, google_api_key=s.api_key, temperature=s.LLM_TEMPERATURE
        )

    if s.LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=s.LLM_MODEL, api_key=s.api_key, temperature=s.LLM_TEMPERATURE)

    raise ValueError(f"Unknown LLM_PROVIDER '{s.LLM_PROVIDER}'. Use 'gemini' or 'openai'.")


def load_prompt(name: str, **values: str) -> str:
    """Read `prompts/{name}.md` and substitute every {{placeholder}}."""
    text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=2, max=30),
    retry=retry_if_exception(lambda e: any(m in str(e).lower() for m in _TRANSIENT)),
    reraise=True,
)
def ask(prompt: str, schema: type[T]) -> T:
    """Send `prompt` to the configured model and return a validated `schema`."""
    logger.info("LLM call -> %s", schema.__name__)
    return get_model().with_structured_output(schema).invoke(prompt)
