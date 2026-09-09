"""Interview questions generated for one screened candidate."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Assessment, Resume, Status
from ..schemas import AssessmentOut
from ..services import create_assessment

router = APIRouter(prefix="/assessments", tags=["assessments"])


@router.post("", response_model=AssessmentOut, status_code=201)
def generate(
    resume_id: int,
    num_questions: int = Query(6, ge=1, le=20),
    db: Session = Depends(get_db),
) -> Assessment:
    """Write a tailored technical round for this candidate."""
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(404, "Resume not found")
    if resume.status != Status.DONE:
        raise HTTPException(400, "This resume has not been screened successfully yet")

    try:
        assessment = create_assessment(db, resume, num_questions)
    except Exception as exc:
        raise HTTPException(502, f"Could not generate questions: {exc}") from None

    db.commit()
    db.refresh(assessment)
    return assessment


@router.get("", response_model=list[AssessmentOut])
def list_for_resume(resume_id: int, db: Session = Depends(get_db)) -> list[Assessment]:
    """Everything generated for this candidate so far, newest first."""
    stmt = (
        select(Assessment)
        .where(Assessment.resume_id == resume_id)
        .order_by(Assessment.created_at.desc(), Assessment.id.desc())
    )
    return list(db.scalars(stmt))
