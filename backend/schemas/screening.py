"""Pydantic schemas for candidate scoring.

The LLM never outputs Fit directly - see backend/core/config.py's
FIT_THRESHOLD_BEST/MEDIUM and backend/services/scoring.py:_compute_fit -
so the threshold can be tuned without touching the prompt.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.core.enums import Fit, ScreeningResultStatus


class ScoringExtractedFields(BaseModel):
    """What the LLM outputs when scoring one candidate against one JD -
    see backend/prompts/score_candidate.md.
    """

    per_skill_scores: dict[str, int] = Field(
        description="Score 0-10 for EVERY must-have and good-to-have skill listed in the JD."
    )
    overall_rating: int = Field(description="Holistic fit score, 0-100.")
    relevant_experience_years: float = Field(
        description=(
            "Years of experience in roles that actually match this JD's requirements - "
            "not the candidate's total career experience."
        )
    )
    reason: str = Field(
        description="2-3 sentences explaining the verdict, grounded in specific resume evidence."
    )


class ScreeningResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: int
    jd_id: int
    jd_version: int
    per_skill_scores: dict[str, int] = Field(default_factory=dict)
    overall_rating: int | None = None
    relevant_experience_years: float | None = None
    fit: Fit | None = None
    reason: str | None = None
    result_status: ScreeningResultStatus
    model_name: str | None = None
    created_at: datetime


class ScreeningTableRow(BaseModel):
    """One row of the results dashboard - a CURRENT ScreeningResult joined
    with its candidate's identifying/profile fields, so the frontend can
    render the whole table without an extra request per row.
    """

    resume_id: int
    candidate_id: int
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    skills: list[str] = Field(default_factory=list)
    total_experience_years: float | None = None
    relevant_experience_years: float | None = None
    per_skill_scores: dict[str, int] = Field(default_factory=dict)
    overall_rating: int | None = None
    fit: Fit | None = None
    reason: str | None = None
    created_at: datetime
