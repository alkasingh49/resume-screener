"""Job descriptions: upload one, review what the AI read, correct it, delete it.

Upload is deliberately synchronous - it is one small file and the recruiter
is sitting there waiting to see whether the parse looks right.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import JobDescription, Resume
from ..schemas import JDBrief, JDEdit, JDOut
from ..services import parse_jd

router = APIRouter(prefix="/jds", tags=["job descriptions"])


@router.post("", response_model=JDOut, status_code=201)
async def upload_jd(file: UploadFile = File(...), db: Session = Depends(get_db)) -> JobDescription:
    """Upload a JD file. The response already contains the parsed fields."""
    settings = get_settings()
    folder = settings.UPLOAD_DIR / "jds"
    folder.mkdir(parents=True, exist_ok=True)

    filename = file.filename or "job-description"
    path = folder / f"{uuid.uuid4().hex}_{Path(filename).name}"
    path.write_bytes(await file.read())

    jd = JobDescription(filename=filename, storage_path=str(path))
    db.add(jd)
    db.flush()

    parse_jd(jd)  # never raises; a failure lands on jd.status/jd.error
    db.commit()
    db.refresh(jd)
    return jd


@router.get("", response_model=list[JDBrief])
def list_jds(db: Session = Depends(get_db)) -> list[JDBrief]:
    """Newest first, each with how many resumes have been uploaded against it."""
    counts = dict(
        db.execute(select(Resume.jd_id, func.count(Resume.id)).group_by(Resume.jd_id)).all()
    )
    jds = db.scalars(select(JobDescription).order_by(JobDescription.created_at.desc())).all()

    briefs = []
    for jd in jds:
        brief = JDBrief.model_validate(jd)
        brief.resume_count = counts.get(jd.id, 0)
        briefs.append(brief)
    return briefs


@router.get("/{jd_id}", response_model=JDOut)
def get_jd(jd_id: int, db: Session = Depends(get_db)) -> JobDescription:
    return _require(db, jd_id)


@router.put("/{jd_id}", response_model=JDOut)
def edit_jd(jd_id: int, edit: JDEdit, db: Session = Depends(get_db)) -> JobDescription:
    """Correct anything the AI got wrong before screening against it."""
    jd = _require(db, jd_id)
    for field, value in edit.model_dump().items():
        setattr(jd, field, value)
    db.commit()
    db.refresh(jd)
    return jd


@router.post("/{jd_id}/reparse", response_model=JDOut)
def reparse_jd(jd_id: int, db: Session = Depends(get_db)) -> JobDescription:
    """Run the AI over this JD again - the retry for a failed parse."""
    jd = _require(db, jd_id)
    parse_jd(jd)
    db.commit()
    db.refresh(jd)
    return jd


@router.delete("/{jd_id}", status_code=204)
def delete_jd(jd_id: int, db: Session = Depends(get_db)) -> None:
    """Deletes the JD and every resume screened against it."""
    db.delete(_require(db, jd_id))
    db.commit()


def _require(db: Session, jd_id: int) -> JobDescription:
    jd = db.get(JobDescription, jd_id)
    if jd is None:
        raise HTTPException(404, "Job description not found")
    return jd
