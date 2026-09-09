"""Screening results: the results dashboard's data.

`GET /screening/results/table` is the main one - a CURRENT ScreeningResult
joined with its candidate's profile fields, one row per candidate, so the
frontend can render the whole table without a request per row.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.enums import ScreeningResultStatus
from backend.db.models.screening_result import ScreeningResult
from backend.db.session import get_db
from backend.schemas.screening import ScreeningResultResponse, ScreeningTableRow
from backend.services.jd import storage as jd_storage
from backend.services.resume import storage as resume_storage

router = APIRouter()


def _current_results_for_jd(db: Session, jd_id: int):
    stmt = (
        select(ScreeningResult)
        .where(ScreeningResult.jd_id == jd_id, ScreeningResult.result_status == ScreeningResultStatus.CURRENT)
        .order_by(ScreeningResult.overall_rating.desc())
    )
    return db.scalars(stmt).all()


@router.get("/screening/results", response_model=list[ScreeningResultResponse])
def list_screening_results(jd_id: int, db: Session = Depends(get_db)) -> list[ScreeningResultResponse]:
    """All CURRENT screening results for one JD, best rating first."""
    jd = jd_storage.get_jd(db, jd_id)
    if jd is None:
        raise HTTPException(status_code=404, detail="JD not found")
    return list(_current_results_for_jd(db, jd_id))


@router.get("/screening/results/table", response_model=list[ScreeningTableRow])
def get_screening_table(jd_id: int, db: Session = Depends(get_db)) -> list[ScreeningTableRow]:
    """The results dashboard table: one row per scored candidate, joined
    with their profile fields, best rating first.
    """
    jd = jd_storage.get_jd(db, jd_id)
    if jd is None:
        raise HTTPException(status_code=404, detail="JD not found")

    rows = []
    for result in _current_results_for_jd(db, jd_id):
        candidate = result.candidate
        rows.append(
            ScreeningTableRow(
                resume_id=candidate.resume_id,
                candidate_id=candidate.id,
                name=candidate.name,
                email=candidate.email,
                phone=candidate.phone,
                skills=candidate.skills or [],
                total_experience_years=candidate.total_experience_years,
                relevant_experience_years=result.relevant_experience_years,
                per_skill_scores=result.per_skill_scores or {},
                overall_rating=result.overall_rating,
                fit=result.fit,
                reason=result.reason,
                created_at=result.created_at,
            )
        )
    return rows


@router.get("/screening/results/by-resume/{resume_id}", response_model=ScreeningResultResponse)
def get_screening_result_for_resume(resume_id: int, db: Session = Depends(get_db)) -> ScreeningResultResponse:
    """The CURRENT screening result for one resume's candidate."""
    resume = resume_storage.get_resume(db, resume_id)
    if resume is None or resume.candidate is None:
        raise HTTPException(status_code=404, detail="No candidate profile for this resume yet")

    stmt = select(ScreeningResult).where(
        ScreeningResult.candidate_id == resume.candidate.id,
        ScreeningResult.result_status == ScreeningResultStatus.CURRENT,
    )
    result = db.scalars(stmt).first()
    if result is None:
        raise HTTPException(status_code=404, detail="No screening result yet for this resume")
    return result
