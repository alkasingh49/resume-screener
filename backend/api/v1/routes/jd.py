"""JD upload / parse / review / confirm.

Upload is single-file and blocking: text extraction and LLM extraction both
run inline in the request, so the response already carries the parsed
result. Extraction failures never raise a 5xx here - they land on the JD row
as status=FAILED with error_message, so the recruiter sees a normal record
they can inspect and re-parse instead of a broken request.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.core.enums import JDStatus
from backend.db.models.job_description import JobDescription
from backend.db.session import get_db
from backend.schemas.jd import JDListItem, JDResponse, JDUpdate
from backend.services.jd import storage
from backend.services.jd.extract import extract_jd_fields
from backend.utils.file_text import FileTextExtractionError, UnsupportedFileTypeError, extract_text

logger = logging.getLogger(__name__)
router = APIRouter()


def _is_complete(jd: JobDescription) -> bool:
    """Minimum bar for a JD to be confirmable / considered fully parsed."""
    return bool(jd.job_title) and bool(jd.must_have_skills)


def _run_extraction(jd: JobDescription) -> None:
    """Text extraction + LLM extraction, mutating `jd` in place. Never
    raises - any failure is captured on the row as status=FAILED.
    """
    try:
        extracted = extract_text(jd.storage_path)
        jd.raw_text = extracted.text
        fields = extract_jd_fields(jd)
        for field_name, value in fields.model_dump().items():
            setattr(jd, field_name, value)
        jd.edited_fields = {}
        jd.error_message = None
        jd.status = JDStatus.PARSED if _is_complete(jd) else JDStatus.NEEDS_REVIEW
    except (UnsupportedFileTypeError, FileTextExtractionError) as exc:
        jd.status = JDStatus.FAILED
        jd.error_message = str(exc)
    except Exception as exc:  # LLM/network/etc - keep the recruiter unblocked
        logger.exception("JD extraction failed for jd_id=%s", jd.id)
        jd.status = JDStatus.FAILED
        jd.error_message = f"Extraction failed: {exc}"


@router.post("/jds/upload", response_model=JDResponse)
async def upload_jd(file: UploadFile = File(...), db: Session = Depends(get_db)) -> JobDescription:
    content = await file.read()
    saved_path = storage.save_upload(content, file.filename)
    jd = storage.create_jd(db, filename=file.filename, storage_path=str(saved_path))
    _run_extraction(jd)
    db.commit()
    db.refresh(jd)
    return jd


@router.get("/jds", response_model=list[JDListItem])
def list_jds(db: Session = Depends(get_db)) -> list[JobDescription]:
    return storage.list_jds(db)


@router.get("/jds/{jd_id}", response_model=JDResponse)
def get_jd(jd_id: int, db: Session = Depends(get_db)) -> JobDescription:
    jd = storage.get_jd(db, jd_id)
    if jd is None:
        raise HTTPException(status_code=404, detail="JD not found")
    return jd


@router.put("/jds/{jd_id}", response_model=JDResponse)
def update_jd(jd_id: int, update: JDUpdate, db: Session = Depends(get_db)) -> JobDescription:
    jd = storage.get_jd(db, jd_id)
    if jd is None:
        raise HTTPException(status_code=404, detail="JD not found")
    storage.apply_edits(db, jd, update)
    db.commit()
    db.refresh(jd)
    return jd


@router.post("/jds/{jd_id}/confirm", response_model=JDResponse)
def confirm_jd(jd_id: int, db: Session = Depends(get_db)) -> JobDescription:
    jd = storage.get_jd(db, jd_id)
    if jd is None:
        raise HTTPException(status_code=404, detail="JD not found")
    if jd.status == JDStatus.CONFIRMED:
        raise HTTPException(status_code=400, detail="JD is already confirmed")
    if not _is_complete(jd):
        raise HTTPException(
            status_code=400, detail="job_title and at least one must-have skill are required to confirm"
        )
    jd.status = JDStatus.CONFIRMED
    jd.confirmed_at = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC, matches other columns
    db.commit()
    db.refresh(jd)
    return jd


@router.post("/jds/{jd_id}/reparse", response_model=JDResponse)
def reparse_jd(jd_id: int, db: Session = Depends(get_db)) -> JobDescription:
    jd = storage.get_jd(db, jd_id)
    if jd is None:
        raise HTTPException(status_code=404, detail="JD not found")
    if jd.status == JDStatus.CONFIRMED:
        raise HTTPException(status_code=400, detail="Cannot re-parse a confirmed JD - edit it instead")
    _run_extraction(jd)
    db.commit()
    db.refresh(jd)
    return jd


@router.delete("/jds/{jd_id}", status_code=204)
def delete_jd(jd_id: int, db: Session = Depends(get_db)) -> None:
    jd = storage.get_jd(db, jd_id)
    if jd is None:
        raise HTTPException(status_code=404, detail="JD not found")
    storage.soft_delete_jd(db, jd)
    db.commit()
