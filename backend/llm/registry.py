"""Provider name -> adapter. Adding a provider means writing
`providers/<name>.py` and adding one line here - never an if/elif chain.
"""

from backend.llm.base import ChatModelBuilder, EmbeddingModelBuilder
from backend.llm.providers import gemini, openai

CHAT_PROVIDERS: dict[str, ChatModelBuilder] = {
    "gemini": gemini.build_chat_model,
    "openai": openai.build_chat_model,
}

EMBEDDING_PROVIDERS: dict[str, EmbeddingModelBuilder] = {
    "gemini": gemini.build_embeddings,
    "openai": openai.build_embeddings,
}
