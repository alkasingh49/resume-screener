"""LLM extraction of a structured candidate profile from raw resume text."""

from backend.core.config import get_settings
from backend.db.models.resume import Resume
from backend.llm.factory import get_chat_model
from backend.llm.structured import extract_structured
from backend.schemas.candidate import CandidateExtractedFields
from backend.utils.prompt_loader import load_prompt


def extract_candidate_fields(resume: Resume) -> CandidateExtractedFields:
    """Run the profile-extraction prompt against `resume.raw_text`.

    Cache key uses the resume's file_hash (not the LLM prompt text) plus the
    JD it's scored against and the model name, per the caching requirement -
    so re-processing the same file against the same JD with the same model
    is free.
    """
    settings = get_settings()
    model = get_chat_model()
    prompt = load_prompt("extract_profile", resume_text=resume.raw_text or "")
    cache_key = f"extract_profile:jd_id={resume.jd_id}:model={settings.LLM_MODEL}:hash={resume.file_hash}"
    return extract_structured(
        model, prompt, CandidateExtractedFields, operation="extract_profile", cache_key=cache_key
    )
