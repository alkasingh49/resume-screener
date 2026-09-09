"""Type aliases/protocols for the LLM abstraction layer.

Services depend on `ChatModel` / `EmbeddingModel` (LangChain's own interfaces)
via dependency injection - never on a concrete provider class.
"""

from typing import Protocol

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from backend.core.config import Settings

# Re-exported so the rest of the app imports these from one place.
ChatModel = BaseChatModel
EmbeddingModel = Embeddings


class ChatModelBuilder(Protocol):
    """Signature every `providers/<name>.py` chat builder must implement."""

    def __call__(self, settings: Settings) -> ChatModel: ...


class EmbeddingModelBuilder(Protocol):
    """Signature every `providers/<name>.py` embedding builder must implement."""

    def __call__(self, settings: Settings) -> EmbeddingModel: ...
