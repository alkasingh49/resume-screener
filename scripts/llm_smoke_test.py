"""Phase 1 proof: run one structured LLM call through the full provider
abstraction (factory -> registry -> provider adapter -> wrapper).

Usage:
    python scripts/llm_smoke_test.py "What is the capital of France?"

To prove the provider swap, change LLM_PROVIDER (+ LLM_MODEL + the matching
API key) in .env and rerun - nothing in this script or in backend/llm/
changes.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel, Field  # noqa: E402

from backend.core.config import get_settings  # noqa: E402
from backend.core.logging import setup_logging  # noqa: E402
from backend.db.session import init_db  # noqa: E402
from backend.llm.factory import get_chat_model  # noqa: E402
from backend.llm.structured import extract_structured  # noqa: E402
from backend.utils.prompt_loader import load_prompt  # noqa: E402


class PingResponse(BaseModel):
    """Trivial schema, just to prove with_structured_output() works end to end."""

    answer: str = Field(description="A short, direct answer to the user's input.")
    confidence: int = Field(description="Confidence in the answer, 0-100.")


def main() -> None:
    setup_logging()
    settings = get_settings()
    settings.ensure_data_dirs()
    init_db()
    user_input = " ".join(sys.argv[1:]) or "What is the capital of France?"

    print(f"provider={settings.LLM_PROVIDER} model={settings.LLM_MODEL}")

    model = get_chat_model()
    prompt = load_prompt("demo_ping", user_input=user_input)
    result = extract_structured(model, prompt, PingResponse, operation="demo_ping")

    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
