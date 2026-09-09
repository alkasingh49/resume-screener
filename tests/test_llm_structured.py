"""Tests for the structured-output chokepoint - no network calls, a fake
chat model stands in for a real LangChain BaseChatModel. Uses an isolated
temp SQLite DB (see conftest.py) since caching now goes through it.
"""

import pytest
from pydantic import BaseModel

from backend.llm import structured


class Answer(BaseModel):
    text: str
    score: int


class _FakeStructuredRunnable:
    def __init__(self, result: Answer):
        self._result = result
        self.invoke_count = 0

    def invoke(self, prompt: str) -> Answer:
        self.invoke_count += 1
        return self._result


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class FakeChatModel:
    """Duck-types just enough of BaseChatModel for extract_structured()."""

    def __init__(self, *, native_supported: bool, result: Answer):
        self.native_supported = native_supported
        self.result = result
        self.plain_invoke_count = 0
        self.structured_runnable = _FakeStructuredRunnable(result)

    def with_structured_output(self, schema):
        if not self.native_supported:
            raise NotImplementedError("this fake model has no native structured output")
        return self.structured_runnable

    def invoke(self, prompt: str) -> _FakeMessage:
        self.plain_invoke_count += 1
        return _FakeMessage(self.result.model_dump_json())


@pytest.fixture(autouse=True)
def _db(isolated_db):
    pass


def test_uses_native_structured_output_when_supported():
    model = FakeChatModel(native_supported=True, result=Answer(text="Paris", score=90))
    result = structured.extract_structured(model, "capital of France?", Answer, operation="test")
    assert result == Answer(text="Paris", score=90)
    assert model.structured_runnable.invoke_count == 1
    assert model.plain_invoke_count == 0


def test_falls_back_to_parser_when_native_unsupported():
    model = FakeChatModel(native_supported=False, result=Answer(text="Paris", score=90))
    result = structured.extract_structured(model, "capital of France?", Answer, operation="test")
    assert result == Answer(text="Paris", score=90)
    assert model.plain_invoke_count == 1


def test_structured_result_is_cached():
    model = FakeChatModel(native_supported=True, result=Answer(text="Paris", score=90))
    key = "fixed-key"
    first = structured.extract_structured(model, "p", Answer, operation="test", cache_key=key)
    second = structured.extract_structured(model, "p", Answer, operation="test", cache_key=key)
    assert first == second
    assert model.structured_runnable.invoke_count == 1  # second served from cache
