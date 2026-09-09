"""Proves the provider abstraction without hitting a real API:
construction is lazy for both providers, switching is env-driven, and an
unknown provider fails loudly.
"""

import pytest

from backend.core.config import get_settings
from backend.llm.factory import get_chat_model, get_embeddings


@pytest.fixture(autouse=True)
def _dummy_api_keys(monkeypatch):
    """Model construction is lazy (no network call), but the pydantic fields
    still need a non-empty value.
    """
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy-google-key")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-openai-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_default_provider_is_gemini(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    get_settings.cache_clear()
    model = get_chat_model()
    assert type(model).__name__ == "ChatGoogleGenerativeAI"


def test_switch_to_openai_via_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    get_settings.cache_clear()
    model = get_chat_model()
    assert type(model).__name__ == "ChatOpenAI"


def test_embeddings_follow_embedding_provider_independently(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "gemini")
    get_settings.cache_clear()
    assert type(get_chat_model()).__name__ == "ChatOpenAI"
    assert type(get_embeddings()).__name__ == "GoogleGenerativeAIEmbeddings"


def test_unknown_chat_provider_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "does-not-exist")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        get_chat_model()


def test_unknown_embedding_provider_raises(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "does-not-exist")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="Unknown EMBEDDING_PROVIDER"):
        get_embeddings()
