"""File storage + CRUD for JobDescription rows. No LLM logic here - see
extract.py for the LLM extraction call.
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.enums import JDStatus, ScreeningResultStatus
from backend.db.models.job_description import JobDescription
from backend.db.models.screening_result import ScreeningResult
from backend.schemas.jd import JDUpdate

_EDITABLE_FIELDS = (
    "job_title",
    "department",
    "location",
    "employment_type",
    "min_years",
    "max_years",
    "must_have_skills",
    "good_to_have_skills",
    "key_responsibilities",
    "qualifications",
)


def save_upload(content: bytes, original_filename: str) -> Path:
    """Write an uploaded JD file to disk under a collision-proof name."""
    settings = get_settings()
    settings.ensure_data_dirs()
    safe_name = f"{uuid.uuid4().hex}_{Path(original_filename).name}"
    path = Path(settings.UPLOAD_DIR_JDS) / safe_name
    path.write_bytes(content)
    return path


def create_jd(db: Session, *, filename: str, storage_path: str) -> JobDescription:
    jd = JobDescription(filename=filename, storage_path=storage_path, status=JDStatus.UPLOADED)
    db.add(jd)
    db.flush()  # assigns jd.id without committing
    return jd


def get_jd(db: Session, jd_id: int) -> JobDescription | None:
    jd = db.get(JobDescription, jd_id)
    if jd is None or jd.deleted_at is not None:
        return None
    return jd


def list_jds(db: Session) -> list[JobDescription]:
    stmt = (
        select(JobDescription)
        .where(JobDescription.deleted_at.is_(None))
        .order_by(JobDescription.created_at.desc())
    )
    return list(db.scalars(stmt))


def soft_delete_jd(db: Session, jd: JobDescription) -> None:
    jd.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC, matches other columns


def apply_edits(db: Session, jd: JobDescription, update: JDUpdate) -> JobDescription:
    """Apply recruiter edits, tracking which fields actually changed
    (edited_fields - so you can see what the LLM got wrong).

    If the JD is already CONFIRMED, editing it bumps `version` and marks any
    existing CURRENT screening results STALE immediately - they were scored
    against the pre-edit content, and jd_version is how a screening result
    stays pinned to the JD snapshot it was actually evaluated against.
    """
    changed = False
    edited_fields = dict(jd.edited_fields or {})
    for field_name in _EDITABLE_FIELDS:
        new_value = getattr(update, field_name)
        if new_value != getattr(jd, field_name):
            setattr(jd, field_name, new_value)
            edited_fields[field_name] = True
            changed = True
    jd.edited_fields = edited_fields

    if changed and jd.status == JDStatus.CONFIRMED:
        jd.version += 1
        stale_stmt = select(ScreeningResult).where(
            ScreeningResult.jd_id == jd.id,
            ScreeningResult.result_status == ScreeningResultStatus.CURRENT,
        )
        for result in db.scalars(stale_stmt):
            result.result_status = ScreeningResultStatus.STALE

    return jd
