"""LLM generation of a targeted technical assessment for one candidate
against the JD their resume was screened for - questions focused on the
overlap between what the JD needs and what the candidate's resume claims,
each tagged with skill + difficulty + expected answer points for the
interviewer.
"""

import logging

from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.db.models.assessment import Assessment
from backend.db.models.candidate import Candidate
from backend.db.models.job_description import JobDescription
from backend.db.models.resume import Resume
from backend.llm.factory import get_chat_model
from backend.llm.structured import extract_structured
from backend.schemas.assessment import AssessmentGeneratedFields
from backend.utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)


def _overlap_skills(jd: JobDescription, candidate: Candidate) -> list[str]:
    """Skills the JD asks for that the candidate's resume also claims -
    what the assessment should actually test. Falls back to the JD's
    must-have skills if there's no overlap at all (e.g. a NO-fit candidate),
    so there's still something concrete to generate questions about.
    """
    jd_skills = {s.lower(): s for s in (jd.must_have_skills or []) + (jd.good_to_have_skills or [])}
    candidate_skills_lower = {s.lower() for s in (candidate.skills or [])}
    overlap = [original for lower, original in jd_skills.items() if lower in candidate_skills_lower]
    return overlap or (jd.must_have_skills or [])


def _build_candidate_summary(candidate: Candidate) -> str:
    # Deliberately not shared with scoring.py's near-identical helper - see
    # the JD/resume flow separation rationale in the project README: each
    # prompt's context needs are free to diverge independently over time.
    lines = [
        f"Name: {candidate.name or 'Unknown'}",
        f"Current title: {candidate.current_title or 'N/A'} at {candidate.current_company or 'N/A'}",
        f"Total experience: "
        f"{candidate.total_experience_years if candidate.total_experience_years is not None else 'Unknown'} years",
        f"Skills: {', '.join(candidate.skills or []) or 'None listed'}",
    ]
    if candidate.work_history:
        history = "; ".join(
            f"{w.get('title', '')} at {w.get('company', '')}: {w.get('description') or 'no description'}"
            for w in candidate.work_history
        )
        lines.append(f"Work history: {history}")
    return "\n".join(lines)


def _generate_via_llm(prompt: str, *, operation: str, cache_key: str) -> AssessmentGeneratedFields:
    """The actual LLM call, split out so tests can mock just this one call
    (same pattern as extract_jd_fields/extract_candidate_fields/_score_via_llm).
    """
    model = get_chat_model()
    return extract_structured(
        model, prompt, AssessmentGeneratedFields, operation=operation, cache_key=cache_key
    )


def generate_assessment(
    db: Session,
    *,
    jd: JobDescription,
    resume: Resume,
    num_easy: int,
    num_medium: int,
    num_hard: int,
) -> Assessment:
    """Generate and persist a new Assessment for `resume`'s candidate.
    Raises if the resume has no extracted candidate profile yet - the
    caller (the API route) turns that into a clean HTTP error.
    """
    candidate = resume.candidate
    if candidate is None:
        raise ValueError(f"resume_id={resume.id} has no extracted candidate profile yet")

    settings = get_settings()
    overlap = _overlap_skills(jd, candidate)
    prompt = load_prompt(
        "generate_assessment",
        job_title=jd.job_title or "",
        must_have_skills=", ".join(jd.must_have_skills or []) or "(none listed)",
        good_to_have_skills=", ".join(jd.good_to_have_skills or []) or "(none listed)",
        key_responsibilities="\n".join(f"- {r}" for r in (jd.key_responsibilities or [])) or "(none listed)",
        candidate_summary=_build_candidate_summary(candidate),
        overlap_skills=", ".join(overlap) or "(no overlap found - use the JD's must-have skills)",
        num_easy=str(num_easy),
        num_medium=str(num_medium),
        num_hard=str(num_hard),
    )

    cache_key = (
        f"assessment:jd_id={jd.id}:jd_version={jd.version}:candidate_id={candidate.id}"
        f":easy={num_easy}:medium={num_medium}:hard={num_hard}:model={settings.LLM_MODEL}"
    )
    fields = _generate_via_llm(prompt, operation="generate_assessment", cache_key=cache_key)

    assessment = Assessment(
        candidate_id=candidate.id,
        jd_id=jd.id,
        questions=[q.model_dump(mode="json") for q in fields.questions],
    )
    db.add(assessment)
    db.flush()
    return assessment
