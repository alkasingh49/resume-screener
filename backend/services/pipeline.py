"""The resume processing pipeline: parse -> score, per resume, with bounded
concurrency for a batch.

This is what actually moves a resume through PENDING -> PARSING -> SCORING
-> DONE/FAILED. Phases 4-6 exercised the PARSING half manually, one resume
at a time via a button; this ties both halves together and runs them
automatically (triggered from resume upload, via FastAPI BackgroundTasks)
with a capped worker pool instead of a click per file.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.enums import JDStatus, ResumeStatus
from backend.db.models.resume import Resume
from backend.db.session import session_scope
from backend.services.jd import storage as jd_storage
from backend.services.resume import storage as resume_storage
from backend.services.resume.profile import process_resume
from backend.services.scoring import score_candidate

logger = logging.getLogger(__name__)


def process_and_score_resume(db: Session, resume: Resume) -> None:
    """Run the full pipeline for one resume: PENDING -> PARSING -> SCORING
    (profile extraction + RAG indexing, backend/services/resume/profile.py)
    -> DONE (scoring) or FAILED at either step. Mutates `resume` in place;
    never raises.
    """
    process_resume(db, resume)
    if resume.status != ResumeStatus.SCORING:
        return  # profile extraction/indexing already failed - nothing to score

    jd = jd_storage.get_jd(db, resume.jd_id)
    if jd is None or jd.status != JDStatus.CONFIRMED:
        resume.status = ResumeStatus.FAILED
        resume.error_message = "JD is no longer confirmed - cannot score against it."
        return

    try:
        score_candidate(db, jd=jd, resume=resume)
        resume.status = ResumeStatus.DONE
        resume.error_message = None
    except Exception as exc:
        logger.exception("Scoring failed for resume_id=%s", resume.id)
        resume.status = ResumeStatus.FAILED
        resume.error_message = f"Scoring failed: {exc}"


def _run_one_in_worker(resume_id: int) -> None:
    """Runs in a worker thread - owns its own short-lived DB session, since
    a SQLAlchemy Session isn't safe to share across concurrent threads.
    """
    try:
        with session_scope() as db:
            resume = resume_storage.get_resume(db, resume_id)
            if resume is None:
                logger.warning("pipeline: resume_id=%s not found, skipping", resume_id)
                return
            process_and_score_resume(db, resume)
    except Exception:
        # Unreachable in practice (process_and_score_resume never raises),
        # but a batch run must never let one resume's worker crash take the
        # rest of the batch down with it.
        logger.exception("pipeline: unexpected error processing resume_id=%s", resume_id)


def run_pipeline_for_jd(jd_id: int, *, max_workers: int | None = None, include_failed: bool = False) -> int:
    """Process every eligible resume for one JD, with bounded concurrency.

    Only PENDING resumes are picked up by default (what the automatic
    upload-triggered run wants); pass `include_failed=True` to also retry
    FAILED ones (what the manual "retry" button wants). Safe to call
    repeatedly - anything already DONE or mid-flight is left alone. Returns
    how many resumes were queued.
    """
    settings = get_settings()
    workers = max_workers or settings.PIPELINE_MAX_WORKERS
    eligible_statuses = (ResumeStatus.PENDING, ResumeStatus.FAILED) if include_failed else (ResumeStatus.PENDING,)

    with session_scope() as db:
        resumes = resume_storage.list_resumes_for_jd(db, jd_id)
        eligible_ids = [r.id for r in resumes if r.status in eligible_statuses]

    if not eligible_ids:
        return 0

    logger.info(
        "pipeline: processing %d resume(s) for jd_id=%s (max_workers=%d, include_failed=%s)",
        len(eligible_ids), jd_id, workers, include_failed,
    )
    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(_run_one_in_worker, eligible_ids))
    return len(eligible_ids)
