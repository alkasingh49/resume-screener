"""LLM scoring of one candidate against the confirmed JD their resume was
uploaded against - per-skill scores, overall rating, relevant (JD-matching)
years of experience, and a grounded reason.

Fit is deliberately never asked of the LLM - it's computed here from
overall_rating using config thresholds (FIT_THRESHOLD_BEST/MEDIUM), so
tuning the cutoffs never requires touching the prompt.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.enums import Fit, ScreeningResultStatus
from backend.db.models.candidate import Candidate
from backend.db.models.job_description import JobDescription
from backend.db.models.resume import Resume
from backend.db.models.screening_result import ScreeningResult
from backend.llm.factory import get_chat_model
from backend.llm.structured import extract_structured
from backend.schemas.screening import ScoringExtractedFields
from backend.services import vectorstore
from backend.utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)


def _compute_fit(overall_rating: int) -> Fit:
    settings = get_settings()
    if overall_rating >= settings.FIT_THRESHOLD_BEST:
        return Fit.BEST
    if overall_rating >= settings.FIT_THRESHOLD_MEDIUM:
        return Fit.MEDIUM
    return Fit.NO


def _build_candidate_summary(candidate: Candidate) -> str:
    lines = [
        f"Name: {candidate.name or 'Unknown'}",
        f"Current title: {candidate.current_title or 'N/A'} at {candidate.current_company or 'N/A'}",
        f"Total experience: "
        f"{candidate.total_experience_years if candidate.total_experience_years is not None else 'Unknown'} years",
        f"Skills: {', '.join(candidate.skills or []) or 'None listed'}",
        f"Certifications: {', '.join(candidate.certifications or []) or 'None listed'}",
    ]
    if candidate.education:
        edu = "; ".join(
            f"{e.get('degree', '')} - {e.get('institution', '')} ({e.get('year', '')})"
            for e in candidate.education
        )
        lines.append(f"Education: {edu}")
    if candidate.work_history:
        history = "; ".join(
            f"{w.get('title', '')} at {w.get('company', '')} "
            f"({w.get('start_date', '')} - {w.get('end_date') or 'Present'})"
            for w in candidate.work_history
        )
        lines.append(f"Work history: {history}")
    return "\n".join(lines)


def _build_evidence_block(jd: JobDescription, resume_id: int) -> str:
    must_have_skills = jd.must_have_skills or []
    if not must_have_skills:
        return "(JD has no must-have skills listed - none retrieved.)"

    chunks_by_skill = vectorstore.retrieve_relevant_chunks_for_skills(jd.id, resume_id, must_have_skills)
    lines = []
    for skill, chunks in chunks_by_skill.items():
        lines.append(f"### Evidence for '{skill}':")
        if chunks:
            lines.extend(f"- {chunk.strip()}" for chunk in chunks)
        else:
            lines.append("- (no matching resume content found)")
    return "\n".join(lines)


def _score_via_llm(prompt: str, *, operation: str, cache_key: str) -> ScoringExtractedFields:
    """The actual LLM call, split out from score_candidate() so tests can
    mock just this one call (same pattern as extract_jd_fields/
    extract_candidate_fields) without needing a real chat model.
    """
    model = get_chat_model()
    return extract_structured(model, prompt, ScoringExtractedFields, operation=operation, cache_key=cache_key)


def score_candidate(db: Session, *, jd: JobDescription, resume: Resume) -> ScreeningResult:
    """Score `resume`'s candidate against `jd`. Requires the resume to
    already have an extracted Candidate profile and indexed RAG chunks
    (i.e. resume.status == SCORING) - raises if not, so the caller
    (services/pipeline.py) can catch it and mark the resume FAILED.

    Creates a new ScreeningResult (result_status=CURRENT) and marks any
    prior CURRENT result for this candidate+JD STALE, preserving history
    rather than overwriting it.
    """
    candidate = resume.candidate
    if candidate is None:
        raise ValueError(f"resume_id={resume.id} has no extracted candidate profile yet")

    settings = get_settings()
    prompt = load_prompt(
        "score_candidate",
        job_title=jd.job_title or "",
        must_have_skills=", ".join(jd.must_have_skills or []) or "(none listed)",
        good_to_have_skills=", ".join(jd.good_to_have_skills or []) or "(none listed)",
        min_years=str(jd.min_years) if jd.min_years is not None else "unspecified",
        max_years=str(jd.max_years) if jd.max_years is not None else "unspecified",
        key_responsibilities="\n".join(f"- {r}" for r in (jd.key_responsibilities or [])) or "(none listed)",
        qualifications=jd.qualifications or "(none listed)",
        candidate_summary=_build_candidate_summary(candidate),
        evidence=_build_evidence_block(jd, resume.id),
    )

    cache_key = f"score:jd_id={jd.id}:jd_version={jd.version}:model={settings.LLM_MODEL}:hash={resume.file_hash}"
    fields = _score_via_llm(prompt, operation="score_candidate", cache_key=cache_key)

    stale_stmt = select(ScreeningResult).where(
        ScreeningResult.candidate_id == candidate.id,
        ScreeningResult.jd_id == jd.id,
        ScreeningResult.result_status == ScreeningResultStatus.CURRENT,
    )
    for old_result in db.scalars(stale_stmt):
        old_result.result_status = ScreeningResultStatus.STALE

    result = ScreeningResult(
        candidate_id=candidate.id,
        jd_id=jd.id,
        jd_version=jd.version,
        per_skill_scores=fields.per_skill_scores,
        overall_rating=fields.overall_rating,
        relevant_experience_years=fields.relevant_experience_years,
        fit=_compute_fit(fields.overall_rating),
        reason=fields.reason,
        result_status=ScreeningResultStatus.CURRENT,
        model_name=settings.LLM_MODEL,
    )
    db.add(result)
    db.flush()
    return result
