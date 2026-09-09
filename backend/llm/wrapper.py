"""Cross-cutting concerns for LLM calls: retry/backoff, caching, call logging.

Sits above the provider adapters so this behaviour survives a provider swap -
`structured.py` (the single chokepoint services call for structured
extraction) routes every model call through `run_with_resilience` here.

Rate limiting is handled separately, at model-construction time in each
`providers/*.py` builder (via LangChain's native `rate_limiter` support), not
in this module - that way it also covers native tool-calling/structured-
output call paths, not just plain `.invoke()`.

Caching and call logging are backed by the `llm_cache` / `llm_call_logs`
tables (backend/db/models/), written via a short-lived DB session per call.
"""

import hashlib
import logging
import time
from typing import Callable, TypeVar

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from backend.core.config import get_settings
from backend.db.models.llm_cache import LLMCacheEntry
from backend.db.models.llm_call_log import LLMCallLog
from backend.db.session import session_scope

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Substrings that mark an exception as transient/worth retrying (rate limits,
# timeouts, transient server errors) rather than a bad request we'd just fail
# again on identically.
_RETRYABLE_MARKERS = ("429", "rate limit", "quota", "timeout", "unavailable", "503", "internal error")


def _hash_key(cache_key: str) -> str:
    return hashlib.sha256(cache_key.encode("utf-8")).hexdigest()


def _cache_get(cache_key: str) -> str | None:
    digest = _hash_key(cache_key)
    with session_scope() as db:
        entry = db.query(LLMCacheEntry).filter_by(cache_key=digest).one_or_none()
        return entry.response_json if entry else None


def _cache_set(cache_key: str, response: str, operation: str) -> None:
    digest = _hash_key(cache_key)
    with session_scope() as db:
        entry = db.query(LLMCacheEntry).filter_by(cache_key=digest).one_or_none()
        if entry is not None:
            entry.response_json = response
        else:
            db.add(LLMCacheEntry(cache_key=digest, operation=operation, response_json=response))


def _log_call(*, operation: str, provider: str, model: str, latency_ms: int, cache_hit: bool) -> None:
    logger.info(
        "llm_call | operation=%s | provider=%s | model=%s | latency_ms=%d | cache_hit=%s",
        operation,
        provider,
        model,
        latency_ms,
        cache_hit,
    )
    with session_scope() as db:
        db.add(
            LLMCallLog(
                provider=provider,
                model=model,
                operation=operation,
                latency_ms=latency_ms,
                cache_hit=cache_hit,
            )
        )


def _is_retryable(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in _RETRYABLE_MARKERS)


def run_with_resilience(
    fn: Callable[[], T],
    *,
    operation: str,
    cache_key: str | None = None,
    to_cache: Callable[[T], str] | None = None,
    from_cache: Callable[[str], T] | None = None,
) -> T:
    """Run one LLM call with retry/backoff, optional caching, and call logging.

    `operation` is a short tag (e.g. "extract_jd", "score_candidate") used in
    logs. Pass `cache_key` + `to_cache` + `from_cache` together to enable
    caching for calls whose result can round-trip through a string (e.g. a
    Pydantic model via `.model_dump_json()` / `.model_validate_json()`);
    omit all three to skip caching.
    """
    settings = get_settings()

    if cache_key and from_cache is not None:
        cached = _cache_get(cache_key)
        if cached is not None:
            _log_call(
                operation=operation,
                provider=settings.LLM_PROVIDER,
                model=settings.LLM_MODEL,
                latency_ms=0,
                cache_hit=True,
            )
            return from_cache(cached)

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential_jitter(initial=1, max=20),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    def _call() -> T:
        return fn()

    start = time.monotonic()
    result = _call()
    latency_ms = int((time.monotonic() - start) * 1000)

    _log_call(
        operation=operation,
        provider=settings.LLM_PROVIDER,
        model=settings.LLM_MODEL,
        latency_ms=latency_ms,
        cache_hit=False,
    )

    if cache_key and to_cache is not None:
        _cache_set(cache_key, to_cache(result), operation)

    return result
