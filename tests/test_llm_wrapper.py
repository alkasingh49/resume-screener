"""Tests for the retry/backoff/cache wrapper - no network calls, DB-backed
cache and call log against an isolated temp SQLite DB (see conftest.py).
"""

import pytest

from backend.llm import wrapper


@pytest.fixture(autouse=True)
def _db(isolated_db):
    pass


def test_returns_result_on_first_success():
    result = wrapper.run_with_resilience(lambda: "ok", operation="test")
    assert result == "ok"


def test_retries_transient_errors_then_succeeds():
    calls = {"count": 0}

    def flaky():
        calls["count"] += 1
        if calls["count"] < 3:
            raise RuntimeError("429 rate limit exceeded")
        return "recovered"

    result = wrapper.run_with_resilience(flaky, operation="test")
    assert result == "recovered"
    assert calls["count"] == 3


def test_non_retryable_error_fails_fast():
    calls = {"count": 0}

    def broken():
        calls["count"] += 1
        raise ValueError("malformed request - missing required field")

    with pytest.raises(ValueError, match="malformed request"):
        wrapper.run_with_resilience(broken, operation="test")
    assert calls["count"] == 1


def test_cache_hit_skips_the_call():
    calls = {"count": 0}

    def expensive():
        calls["count"] += 1
        return "computed"

    key = "same-key"
    first = wrapper.run_with_resilience(
        expensive, operation="test", cache_key=key, to_cache=str, from_cache=str
    )
    second = wrapper.run_with_resilience(
        expensive, operation="test", cache_key=key, to_cache=str, from_cache=str
    )

    assert first == second == "computed"
    assert calls["count"] == 1  # second call served from cache


def test_different_cache_keys_do_not_collide():
    result_a = wrapper.run_with_resilience(
        lambda: "a", operation="test", cache_key="key-a", to_cache=str, from_cache=str
    )
    result_b = wrapper.run_with_resilience(
        lambda: "b", operation="test", cache_key="key-b", to_cache=str, from_cache=str
    )
    assert (result_a, result_b) == ("a", "b")
