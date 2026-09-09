"""Technical assessment generation for a candidate, targeted at the overlap
between the JD's requirements and their actual resume background.

Export (Markdown/CSV, interviewer vs. candidate-facing with answer points
stripped) is built client-side in the frontend from the questions this
returns - see frontend/pages/4_Assessments.py - no export-specific backend
endpoints needed.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models.assessment import Assessment
from backend.db.session import get_db
from backend.schemas.assessment import AssessmentGenerateRequest, AssessmentResponse
from backend.services.assessment import generate_assessment
from backend.services.jd import storage as jd_storage
from backend.services.resume import storage as resume_storage

router = APIRouter()


@router.post("/assessments/generate", response_model=AssessmentResponse)
def generate(request: AssessmentGenerateRequest, db: Session = Depends(get_db)) -> Assessment:
    if request.num_easy + request.num_medium + request.num_hard <= 0:
        raise HTTPException(status_code=400, detail="Request at least one question")

    resume = resume_storage.get_resume(db, request.resume_id)
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    if resume.candidate is None:
        raise HTTPException(status_code=404, detail="No candidate profile extracted yet for this resume")

    jd = jd_storage.get_jd(db, resume.jd_id)
    if jd is None:
        raise HTTPException(status_code=404, detail="JD not found")

    try:
        assessment = generate_assessment(
            db,
            jd=jd,
            resume=resume,
            num_easy=request.num_easy,
            num_medium=request.num_medium,
            num_hard=request.num_hard,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Assessment generation failed: {exc}") from None

    db.commit()
    db.refresh(assessment)
    return assessment


@router.get("/assessments", response_model=list[AssessmentResponse])
def list_assessments(resume_id: int, db: Session = Depends(get_db)) -> list[Assessment]:
    """All past assessments for one resume's candidate, newest first."""
    resume = resume_storage.get_resume(db, resume_id)
    if resume is None or resume.candidate is None:
        raise HTTPException(status_code=404, detail="No candidate profile for this resume")
    # id as a tiebreaker: created_at has only second-level resolution in
    # SQLite, so two assessments generated within the same second would
    # otherwise sort in an unstable order.
    stmt = (
        select(Assessment)
        .where(Assessment.candidate_id == resume.candidate.id)
        .order_by(Assessment.created_at.desc(), Assessment.id.desc())
    )
    return list(db.scalars(stmt))


@router.get("/assessments/{assessment_id}", response_model=AssessmentResponse)
def get_assessment(assessment_id: int, db: Session = Depends(get_db)) -> Assessment:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return assessment
