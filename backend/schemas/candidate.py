"""Pydantic schemas for candidate profile extraction. Deliberately separate
from the resume upload schemas - see backend/schemas/resume.py.
"""

from pydantic import BaseModel, ConfigDict, Field

from backend.core.enums import ExperienceSource


class EducationEntry(BaseModel):
    degree: str | None = Field(default=None, description="e.g. 'B.Tech in Computer Science'.")
    institution: str | None = Field(default=None, description="School/university name.")
    year: str | None = Field(default=None, description="Graduation year or year range, as written.")


class WorkHistoryEntry(BaseModel):
    title: str | None = Field(default=None, description="Job title held in this role.")
    company: str | None = Field(default=None, description="Employer name.")
    start_date: str | None = Field(
        default=None, description="As written in the resume, e.g. 'Jan 2020', '2020', '03/2019'."
    )
    end_date: str | None = Field(
        default=None, description="As written, or 'Present' for an ongoing role. Null if not stated."
    )
    description: str | None = Field(default=None, description="Brief summary of responsibilities, if stated.")


class CandidateExtractedFields(BaseModel):
    """What the LLM extracts from raw resume text - see
    backend/prompts/extract_profile.md.

    `total_experience_years` here is the LLM's own estimate. The
    authoritative figure is computed from `work_history` dates by
    backend/utils/dates.py; this field is only used as a fallback when that
    computation isn't possible (see backend/services/resume/profile.py).
    """

    name: str | None = Field(default=None, description="Candidate's full name.")
    email: str | None = Field(default=None, description="Primary email address.")
    phone: str | None = Field(default=None, description="Primary phone number, as written.")
    location: str | None = Field(default=None, description="City/region, if stated.")
    current_title: str | None = Field(default=None, description="Most recent/current job title.")
    current_company: str | None = Field(default=None, description="Most recent/current employer.")
    total_experience_years: float | None = Field(
        default=None, description="Best estimate of total years of professional experience."
    )
    skills: list[str] = Field(default_factory=list, description="Technical and professional skills mentioned.")
    education: list[EducationEntry] = Field(default_factory=list)
    work_history: list[WorkHistoryEntry] = Field(
        default_factory=list, description="Most recent role first."
    )
    certifications: list[str] = Field(default_factory=list)


class CandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resume_id: int
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    current_title: str | None = None
    current_company: str | None = None
    total_experience_years: float | None = None
    total_experience_source: ExperienceSource | None = None
    skills: list[str] = Field(default_factory=list)
    education: list[dict] = Field(default_factory=list)
    work_history: list[dict] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
