"""Loads prompt templates from backend/prompts/*.md at runtime.

Prompts are plain markdown with `{{placeholder}}` substitution (double
braces, deliberately - our prompts embed JSON output examples full of single
braces, and `{{...}}` lets those pass through untouched instead of needing
`str.format`-style escaping) - never inline strings in Python, never
provider-specific.
"""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(name: str, **kwargs: str) -> str:
    """Load `backend/prompts/{name}.md` and fill in any `{{placeholder}}` values."""
    path = _PROMPTS_DIR / f"{name}.md"
    template = path.read_text(encoding="utf-8")
    for key, value in kwargs.items():
        template = template.replace(f"{{{{{key}}}}}", value)
    return template
