"""What the app actually does: parse a JD, screen a resume against it, and
write interview questions for a candidate.

Every function here records failure on the row it is working on rather than
raising. One unreadable resume in a batch of fifty must never take down the
other forty-nine - it shows up in the table as FAILED with a reason.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from .config import get_settings
from .database import session
from .files import UnreadableFile, extract_text
from .llm import ask, load_prompt
from .models import Assessment, Fit, JobDescription, Resume, Status
from .schemas import LLMJobDescription, LLMQuestionSet, LLMScreening

logger = logging.getLogger(__name__)


def fit_for(score: int) -> str:
    """Map the 0-100 rating onto Best / Medium / No.

    Deliberately computed here from config thresholds rather than asked of
    the LLM, so retuning the cutoffs never means editing a prompt.
    """
    s = get_settings()
    if score >= s.FIT_BEST_MIN:
        return Fit.BEST
    if score >= s.FIT_MEDIUM_MIN:
        return Fit.MEDIUM
    return Fit.NO


# --------------------------------------------------------------- job descriptions ---


def parse_jd(jd: JobDescription) -> None:
    """Read the uploaded file and pull the JD's fields out of it. Mutates
    `jd` in place; the caller commits."""
    jd.status = Status.PROCESSING
    try:
        jd.raw_text = extract_text(jd.storage_path)
        fields = ask(load_prompt("extract_jd", jd_text=jd.raw_text), LLMJobDescription)

        jd.title = fields.title
        jd.location = fields.location
        jd.min_years = fields.min_years
        jd.max_years = fields.max_years
        jd.must_have_skills = fields.must_have_skills
        jd.good_to_have_skills = fields.good_to_have_skills
        jd.responsibilities = fields.responsibilities

        jd.error = None
        jd.status = Status.DONE
    except UnreadableFile as exc:
        jd.status, jd.error = Status.FAILED, str(exc)
    except Exception as exc:
        logger.exception("JD %s failed to parse", jd.id)
        jd.status, jd.error = Status.FAILED, f"Could not analyse this job description: {exc}"


# ------------------------------------------------------------------------ screening ---


def _years_wanted(jd: JobDescription) -> str:
    if jd.min_years and jd.max_years:
        return f"{jd.min_years:g}-{jd.max_years:g} years"
    if jd.min_years:
        return f"{jd.min_years:g}+ years"
    return "not specified"


def screen_resume(resume: Resume, jd: JobDescription) -> None:
    """Extract the candidate's details AND score them against `jd`, in a
    single LLM call. Mutates `resume` in place; the caller commits."""
    resume.status = Status.PROCESSING
    try:
        if not resume.raw_text:
            resume.raw_text = extract_text(resume.storage_path)

        prompt = load_prompt(
            "screen_resume",
            job_title=jd.title or "(untitled role)",
            job_location=jd.location or "not specified",
            years_required=_years_wanted(jd),
            must_have_skills=", ".join(jd.must_have_skills) or "(none listed)",
            good_to_have_skills=", ".join(jd.good_to_have_skills) or "(none listed)",
            responsibilities="\n".join(f"- {r}" for r in jd.responsibilities) or "- (none listed)",
            resume_text=resume.raw_text,
        )
        result = ask(prompt, LLMScreening)

        resume.name = result.name
        resume.email = result.email
        resume.phone = result.phone
        resume.location = result.location
        resume.current_title = result.current_title
        resume.current_company = result.current_company
        resume.total_experience_years = result.total_experience_years
        resume.relevant_experience_years = result.relevant_experience_years
        resume.skills = result.skills
        resume.skill_scores = {s.skill: s.score for s in result.skill_scores}
        resume.score = result.score
        resume.fit = fit_for(result.score)
        resume.reason = result.reason

        resume.error = None
        resume.status = Status.DONE
    except UnreadableFile as exc:
        resume.status, resume.error = Status.FAILED, str(exc)
    except Exception as exc:
        logger.exception("Resume %s failed to screen", resume.id)
        resume.status, resume.error = Status.FAILED, f"Could not screen this resume: {exc}"


def _screen_by_id(resume_id: int) -> None:
    """One unit of background work. Owns its own session, because a
    SQLAlchemy Session cannot be shared across threads."""
    try:
        with session() as db:
            resume = db.get(Resume, resume_id)
            if resume is not None:
                screen_resume(resume, resume.jd)
    except Exception:
        logger.exception("Background screening crashed for resume %s", resume_id)


def screen_batch(resume_ids: list[int]) -> None:
    """Screen many resumes at once, a few at a time so we stay inside the
    provider's rate limit. Runs in a background task after upload responds."""
    if not resume_ids:
        return
    workers = min(get_settings().MAX_PARALLEL_RESUMES, len(resume_ids))
    logger.info("Screening %d resume(s), %d at a time", len(resume_ids), workers)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(_screen_by_id, resume_ids))


# ---------------------------------------------------------------------- assessment ---


def create_assessment(db: Session, resume: Resume, num_questions: int) -> Assessment:
    """Write interview questions for one screened candidate. Raises on
    failure - the route turns that into an HTTP error, because unlike
    screening this is a single deliberate action the user is waiting on."""
    jd = resume.jd
    prompt = load_prompt(
        "generate_questions",
        job_title=jd.title or "(untitled role)",
        must_have_skills=", ".join(jd.must_have_skills) or "(none listed)",
        responsibilities="\n".join(f"- {r}" for r in jd.responsibilities) or "- (none listed)",
        candidate_name=resume.name or "the candidate",
        current_role=f"{resume.current_title or 'unknown'} at {resume.current_company or 'unknown'}",
        total_experience=f"{resume.total_experience_years:g}"
        if resume.total_experience_years
        else "unknown",
        candidate_skills=", ".join(resume.skills) or "(none listed)",
        reason=resume.reason or "(not screened yet)",
        resume_text=resume.raw_text or "",
        num_questions=str(num_questions),
    )
    result = ask(prompt, LLMQuestionSet)

    assessment = Assessment(
        resume_id=resume.id, questions=[q.model_dump() for q in result.questions]
    )
    db.add(assessment)
    db.flush()
    return assessment
