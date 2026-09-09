"""File storage + CRUD for Resume rows. No LLM/parsing logic here - the
background pipeline (Phase 5+7) is what moves a row's status past PENDING.
"""

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.enums import ResumeStatus
from backend.db.models.resume import Resume


def save_upload(content: bytes, original_filename: str) -> Path:
    """Write an uploaded resume file to disk under a collision-proof name."""
    settings = get_settings()
    settings.ensure_data_dirs()
    safe_name = f"{uuid.uuid4().hex}_{Path(original_filename).name}"
    path = Path(settings.UPLOAD_DIR_RESUMES) / safe_name
    path.write_bytes(content)
    return path


def create_resume(
    db: Session,
    *,
    jd_id: int,
    filename: str,
    storage_path: str,
    file_size: int,
    mime_type: str | None,
    file_hash: str | None,
    status: ResumeStatus = ResumeStatus.PENDING,
    error_message: str | None = None,
) -> Resume:
    resume = Resume(
        jd_id=jd_id,
        filename=filename,
        storage_path=storage_path,
        file_size=file_size,
        mime_type=mime_type,
        file_hash=file_hash,
        status=status,
        error_message=error_message,
    )
    db.add(resume)
    db.flush()  # assigns resume.id without committing
    return resume


def list_resumes_for_jd(db: Session, jd_id: int) -> list[Resume]:
    stmt = select(Resume).where(Resume.jd_id == jd_id).order_by(Resume.created_at.asc())
    return list(db.scalars(stmt))


def get_resume(db: Session, resume_id: int) -> Resume | None:
    return db.get(Resume, resume_id)
