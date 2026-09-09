"""Single chokepoint for structured LLM extraction.

Every service that needs schema-validated output from the model (JD
extraction, resume/profile extraction, scoring, assessment generation) calls
`extract_structured()` - never `model.with_structured_output()` directly.
"""

import logging
from typing import TypeVar

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel

from backend.llm.base import ChatModel
from backend.llm.wrapper import run_with_resilience

logger = logging.getLogger(__name__)

SchemaT = TypeVar("SchemaT", bound=BaseModel)


def extract_structured(
    model: ChatModel,
    prompt: str,
    schema: type[SchemaT],
    *,
    operation: str,
    cache_key: str | None = None,
) -> SchemaT:
    """Return a `schema` instance populated from the model's response to `prompt`.

    Tries the model's native structured output (tool calling / JSON mode)
    first; falls back to a PydanticOutputParser with format instructions
    appended to the prompt for models/providers that don't support it. The
    whole call is wrapped with retry/backoff, optional caching, and logging
    via `wrapper.run_with_resilience`.
    """

    def _call() -> SchemaT:
        try:
            structured_model = model.with_structured_output(schema)
            return structured_model.invoke(prompt)
        except NotImplementedError:
            logger.warning(
                "operation=%s | native structured output unsupported, using parser fallback", operation
            )
            parser = PydanticOutputParser(pydantic_object=schema)
            full_prompt = f"{prompt}\n\n{parser.get_format_instructions()}"
            raw = model.invoke(full_prompt)
            return parser.parse(raw.content)

    return run_with_resilience(
        _call,
        operation=operation,
        cache_key=cache_key,
        to_cache=lambda result: result.model_dump_json(),
        from_cache=lambda cached: schema.model_validate_json(cached),
    )
