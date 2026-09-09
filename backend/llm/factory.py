"""The only place LLM_PROVIDER / EMBEDDING_PROVIDER are read to construct a
model. Everything else in the app calls get_chat_model()/get_embeddings()
and depends on the returned LangChain interface types, never a concrete
provider class.
"""

from backend.core.config import get_settings
from backend.llm.base import ChatModel, EmbeddingModel
from backend.llm.registry import CHAT_PROVIDERS, EMBEDDING_PROVIDERS


def get_chat_model() -> ChatModel:
    """Build the configured chat model (LLM_PROVIDER + LLM_MODEL)."""
    settings = get_settings()
    try:
        builder = CHAT_PROVIDERS[settings.LLM_PROVIDER]
    except KeyError:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{settings.LLM_PROVIDER}'. Available: {sorted(CHAT_PROVIDERS)}"
        ) from None
    return builder(settings)


def get_embeddings() -> EmbeddingModel:
    """Build the configured embeddings model (EMBEDDING_PROVIDER + EMBEDDING_MODEL)."""
    settings = get_settings()
    try:
        builder = EMBEDDING_PROVIDERS[settings.EMBEDDING_PROVIDER]
    except KeyError:
        raise ValueError(
            f"Unknown EMBEDDING_PROVIDER '{settings.EMBEDDING_PROVIDER}'. "
            f"Available: {sorted(EMBEDDING_PROVIDERS)}"
        ) from None
    return builder(settings)
