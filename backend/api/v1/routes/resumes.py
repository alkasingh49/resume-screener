"""Bulk resume upload against a confirmed JD, per-file status, and manual
processing triggers.

Upload validates and stores each file synchronously (fast, so a bulk batch
returns quickly), then queues the JD's full pipeline (parse -> score) as a
FastAPI background task - so resumes start processing automatically, with
no manual step required. `POST /resumes/{id}/process` and
`POST /resumes/pipeline/run` exist alongside that for manual
retry/demo/testing: same underlying `services.pipeline` functions, just
synchronous and callable on demand. A bad file never aborts a batch or a
processing run - it's marked FAILED with an error message and the rest
continue.
"""

import logging
import mimetypes
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.core.enums import JDStatus, ResumeStatus
from backend.db.session import get_db
from backend.schemas.candidate import CandidateResponse
from backend.schemas.resume import ResumeResponse, ResumeUploadBatchResponse
from backend.services import pipeline
from backend.services.jd import storage as jd_storage
from backend.services.resume import storage as resume_storage
from backend.utils.file_text import SUPPORTED_EXTENSIONS
from backend.utils.hashing import sha256_file

logger = logging.getLogger(__name__)
router = APIRouter()


def _guess_mime_type(filename: str, declared: str | None) -> str | None:
    if declared and declared != "application/octet-stream":
        return declared
    return mimetypes.guess_type(filename)[0] or declared


@router.post("/resumes/upload", response_model=ResumeUploadBatchResponse)
async def upload_resumes(
    jd_id: int,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> ResumeUploadBatchResponse:
    jd = jd_storage.get_jd(db, jd_id)
    if jd is None:
        raise HTTPException(status_code=404, detail="JD not found")
    if jd.status != JDStatus.CONFIRMED:
        raise HTTPException(status_code=400, detail="JD must be CONFIRMED before uploading resumes against it")
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    results: list[ResumeResponse] = []
    for upload in files:
        try:
            resume = await _store_one(db, jd_id=jd_id, upload=upload)
        except Exception:
            # A storage-level failure (disk full, unreadable upload, ...) for
            # ONE file must never abort the rest of the batch.
            logger.exception("Failed to store resume upload '%s' for jd_id=%s", upload.filename, jd_id)
            resume = resume_storage.create_resume(
                db,
                jd_id=jd_id,
                filename=upload.filename or "unknown",
                storage_path="",
                file_size=0,
                mime_type=None,
                file_hash=None,
                status=ResumeStatus.FAILED,
                error_message="Could not store the uploaded file.",
            )
        results.append(ResumeResponse.model_validate(resume))

    db.commit()

    # Kick off parsing + scoring for the newly-PENDING resumes after the
    # response is sent - the recruiter doesn't wait for it, and the status
    # table just polls GET /resumes for progress.
    background_tasks.add_task(pipeline.run_pipeline_for_jd, jd_id)

    failed = sum(1 for r in results if r.status == ResumeStatus.FAILED)
    return ResumeUploadBatchResponse(
        jd_id=jd_id, uploaded=len(results) - failed, failed=failed, resumes=results
    )


async def _store_one(db: Session, *, jd_id: int, upload: UploadFile):
    """Always store the raw file first (matches the JD flow, and the "store
    raw file, filename, size, mime type, status" requirement applies
    regardless of whether the file turns out to be processable) - only THEN
    decide PENDING vs. an immediate FAILED for a type we already know we
    can't parse.
    """
    content = await upload.read()
    filename = upload.filename or "unknown"
    suffix = Path(filename).suffix.lower()
    saved_path = resume_storage.save_upload(content, filename)

    if suffix not in SUPPORTED_EXTENSIONS:
        return resume_storage.create_resume(
            db,
            jd_id=jd_id,
            filename=filename,
            storage_path=str(saved_path),
            file_size=len(content),
            mime_type=upload.content_type,
            file_hash=sha256_file(saved_path),
            status=ResumeStatus.FAILED,
            error_message=(
                f"Unsupported file type '{suffix or '(no extension)'}'. "
                f"Supported: {sorted(SUPPORTED_EXTENSIONS)}."
            ),
        )

    return resume_storage.create_resume(
        db,
        jd_id=jd_id,
        filename=filename,
        storage_path=str(saved_path),
        file_size=len(content),
        mime_type=_guess_mime_type(filename, upload.content_type),
        file_hash=sha256_file(saved_path),
        status=ResumeStatus.PENDING,
    )


@router.get("/resumes", response_model=list[ResumeResponse])
def list_resumes(jd_id: int, db: Session = Depends(get_db)) -> list[ResumeResponse]:
    jd = jd_storage.get_jd(db, jd_id)
    if jd is None:
        raise HTTPException(status_code=404, detail="JD not found")
    return resume_storage.list_resumes_for_jd(db, jd_id)


@router.get("/resumes/{resume_id}", response_model=ResumeResponse)
def get_resume(resume_id: int, db: Session = Depends(get_db)) -> ResumeResponse:
    resume = resume_storage.get_resume(db, resume_id)
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume


@router.post("/resumes/{resume_id}/process", response_model=ResumeResponse)
def process_resume_now(resume_id: int, db: Session = Depends(get_db)) -> ResumeResponse:
    """Manually (re)run the full parse+score pipeline for one resume,
    synchronously - a retry tool for a resume that ended up FAILED, or a way
    to demo/test without waiting on the background task.
    """
    resume = resume_storage.get_resume(db, resume_id)
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    if resume.status not in (ResumeStatus.PENDING, ResumeStatus.FAILED):
        raise HTTPException(
            status_code=400, detail=f"Resume status is {resume.status.value}, nothing to (re)process"
        )
    pipeline.process_and_score_resume(db, resume)
    db.commit()
    db.refresh(resume)
    return resume


@router.post("/resumes/pipeline/run")
def run_pipeline_now(jd_id: int, db: Session = Depends(get_db)) -> dict:
    """Manually run the pipeline for every PENDING or FAILED resume under
    one JD, synchronously (bounded concurrency, same as the automatic
    upload-triggered run) - a batch retry tool, e.g. after fixing a missing
    API key or a transient outage.
    """
    jd = jd_storage.get_jd(db, jd_id)
    if jd is None:
        raise HTTPException(status_code=404, detail="JD not found")
    queued = pipeline.run_pipeline_for_jd(jd_id, include_failed=True)
    return {"jd_id": jd_id, "queued": queued}


@router.get("/resumes/{resume_id}/candidate", response_model=CandidateResponse)
def get_resume_candidate(resume_id: int, db: Session = Depends(get_db)) -> CandidateResponse:
    resume = resume_storage.get_resume(db, resume_id)
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    if resume.candidate is None:
        raise HTTPException(status_code=404, detail="No candidate profile extracted yet for this resume")
    return resume.candidate
