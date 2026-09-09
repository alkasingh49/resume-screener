"""LLM extraction of structured JD fields from raw JD text."""

from backend.core.config import get_settings
from backend.db.models.job_description import JobDescription
from backend.llm.factory import get_chat_model
from backend.llm.structured import extract_structured
from backend.schemas.jd import JDExtractedFields
from backend.utils.hashing import sha256_text
from backend.utils.prompt_loader import load_prompt


def extract_jd_fields(jd: JobDescription) -> JDExtractedFields:
    """Run the JD extraction prompt against `jd.raw_text`.

    Caller (backend/api/v1/routes/jd.py) is responsible for catching
    failures and marking the JD row FAILED - this function lets them
    propagate.
    """
    settings = get_settings()
    model = get_chat_model()
    prompt = load_prompt("extract_jd", jd_text=jd.raw_text or "")
    cache_key = f"extract_jd:jd_id={jd.id}:model={settings.LLM_MODEL}:hash={sha256_text(jd.raw_text or '')}"
    return extract_structured(
        model, prompt, JDExtractedFields, operation="extract_jd", cache_key=cache_key
    )
