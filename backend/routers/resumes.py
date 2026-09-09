"""Resumes: bulk upload against a JD, then read back the screening results.

Upload stores every file quickly and returns, then screens them in the
background - the recruiter drops fifty resumes and watches the table fill
in, rather than staring at a spinner for five minutes. There is no separate
"results" endpoint: the resume row IS the result.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..files import SUPPORTED
from ..models import JobDescription, Resume, Status
from ..schemas import ResumeOut, UploadSummary
from ..services import screen_batch, screen_resume

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.post("", response_model=UploadSummary, status_code=201)
async def upload_resumes(
    jd_id: int,
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> UploadSummary:
    """Bulk-upload resumes for one JD. Screening starts automatically."""
    jd = db.get(JobDescription, jd_id)
    if jd is None:
        raise HTTPException(404, "Job description not found")
    if jd.status != Status.DONE:
        raise HTTPException(400, "Analyse the job description successfully before uploading resumes")
    if not files:
        raise HTTPException(400, "No files were uploaded")

    folder = get_settings().UPLOAD_DIR / "resumes"
    folder.mkdir(parents=True, exist_ok=True)

    created: list[Resume] = []
    for upload in files:
        filename = upload.filename or "resume"
        path = folder / f"{uuid.uuid4().hex}_{Path(filename).name}"
        path.write_bytes(await upload.read())

        resume = Resume(jd_id=jd_id, filename=filename, storage_path=str(path))
        # Reject an unsupported type up front, so it shows in the table with
        # a reason instead of burning an LLM call to fail.
        if Path(filename).suffix.lower() not in SUPPORTED:
            resume.status = Status.FAILED
            resume.error = (
                f"Unsupported file type. Supported: {', '.join(sorted(SUPPORTED))}."
            )
        db.add(resume)
        created.append(resume)

    db.commit()
    for resume in created:
        db.refresh(resume)

    to_screen = [r.id for r in created if r.status == Status.PENDING]
    background.add_task(screen_batch, to_screen)

    rejected = len(created) - len(to_screen)
    return UploadSummary(
        jd_id=jd_id,
        uploaded=len(to_screen),
        rejected=rejected,
        resumes=[ResumeOut.model_validate(r) for r in created],
    )


@router.get("", response_model=list[ResumeOut])
def list_resumes(jd_id: int, db: Session = Depends(get_db)) -> list[Resume]:
    """The screening results table: every resume for a JD, best score first.

    The frontend polls this while a batch is processing.
    """
    stmt = (
        select(Resume)
        .where(Resume.jd_id == jd_id)
        .order_by(Resume.score.desc().nullslast(), Resume.created_at.asc())
    )
    return list(db.scalars(stmt))


@router.get("/{resume_id}", response_model=ResumeOut)
def get_resume(resume_id: int, db: Session = Depends(get_db)) -> Resume:
    return _require(db, resume_id)


@router.post("/{resume_id}/rescreen", response_model=ResumeOut)
def rescreen(resume_id: int, db: Session = Depends(get_db)) -> Resume:
    """Screen one resume again, synchronously - the retry button for a row
    that failed because of a bad API key or a rate limit."""
    resume = _require(db, resume_id)
    screen_resume(resume, resume.jd)
    db.commit()
    db.refresh(resume)
    return resume


@router.delete("/{resume_id}", status_code=204)
def delete_resume(resume_id: int, db: Session = Depends(get_db)) -> None:
    db.delete(_require(db, resume_id))
    db.commit()


def _require(db: Session, resume_id: int) -> Resume:
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(404, "Resume not found")
    return resume
