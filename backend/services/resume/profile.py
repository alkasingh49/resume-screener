"""Per-resume processing: text extraction -> LLM profile extraction ->
total-experience computation -> RAG indexing -> Candidate row.

Never raises - failures are captured on the Resume row as FAILED, the same
pattern the JD flow uses. This is deliberately its own function (not inline
in a route) so the Phase 7 background pipeline can call it directly without
going through HTTP - a route in api/v1/routes/resumes.py just wraps it for
a manual/synchronous trigger until that pipeline exists.
"""

import logging

from sqlalchemy.orm import Session

from backend.core.enums import ExperienceSource, ResumeStatus
from backend.db.models.candidate import Candidate
from backend.db.models.resume import Resume
from backend.services import vectorstore
from backend.services.resume.extract import extract_candidate_fields
from backend.utils.dates import compute_total_experience_years
from backend.utils.file_text import FileTextExtractionError, UnsupportedFileTypeError, extract_text

logger = logging.getLogger(__name__)


def process_resume(db: Session, resume: Resume) -> None:
    """Extract text + candidate profile for one resume, mutating `resume`
    and creating/updating its Candidate row in place, then chunk + embed the
    resume text into the JD-scoped Chroma collection (RAG) so Phase 7's
    scoring step can retrieve skill-relevant chunks instead of the whole
    resume. Leaves resume.status at SCORING on success (awaiting Phase 7) or
    FAILED with error_message on any failure - including an indexing
    failure, since a resume without indexed chunks isn't actually ready to
    be scored.
    """
    resume.status = ResumeStatus.PARSING
    try:
        if not resume.raw_text:
            extracted = extract_text(resume.storage_path)
            resume.raw_text = extracted.text

        fields = extract_candidate_fields(resume)
        work_history = [entry.model_dump() for entry in fields.work_history]
        computed_years = compute_total_experience_years(work_history)

        if computed_years is not None:
            total_years, source = computed_years, ExperienceSource.COMPUTED
        else:
            total_years, source = fields.total_experience_years, ExperienceSource.LLM_FALLBACK

        # Index BEFORE writing the Candidate row: if this fails, nothing
        # candidate-shaped should exist yet for a resume that isn't actually
        # ready to be scored (the route commits whatever's in the session
        # even on failure, so ordering here is what keeps FAILED resumes
        # from ending up with a misleadingly "complete" candidate record).
        vectorstore.index_resume(resume.jd_id, resume.id, resume.raw_text or "")

        candidate = resume.candidate
        if candidate is None:
            candidate = Candidate()
            resume.candidate = candidate  # sets candidate.resume_id AND keeps
            # resume.candidate correctly populated for the rest of THIS
            # session (e.g. scoring.py reads it right after) - constructing
            # Candidate(resume_id=resume.id) + db.add() instead would set the
            # FK but leave the in-memory relationship cache stale until a
            # fresh query, silently breaking same-session reads.

        candidate.name = fields.name
        candidate.email = fields.email
        candidate.phone = fields.phone
        candidate.location = fields.location
        candidate.current_title = fields.current_title
        candidate.current_company = fields.current_company
        candidate.total_experience_years = total_years
        candidate.total_experience_source = source
        candidate.skills = fields.skills
        candidate.education = [entry.model_dump() for entry in fields.education]
        candidate.work_history = work_history
        candidate.certifications = fields.certifications
        db.flush()  # assigns candidate.id - callers (e.g. scoring.py) need it right after

        resume.error_message = None
        resume.status = ResumeStatus.SCORING
    except (UnsupportedFileTypeError, FileTextExtractionError) as exc:
        resume.status = ResumeStatus.FAILED
        resume.error_message = str(exc)
    except Exception as exc:  # LLM/network/etc - keep the batch unblocked
        logger.exception("Resume processing failed for resume_id=%s", resume.id)
        resume.status = ResumeStatus.FAILED
        resume.error_message = f"Processing failed: {exc}"
