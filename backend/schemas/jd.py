"""Pydantic schemas for the JD flow: the LLM extraction schema and the API
request/response shapes. Deliberately separate from the resume schemas -
see backend/schemas/resume.py (Phase 5).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.core.enums import JDStatus


class JDExtractedFields(BaseModel):
    """What the LLM extracts from raw JD text - see backend/prompts/extract_jd.md.

    Reused as the base for the API's update/response shapes below, since the
    editable fields in the review form ARE exactly the extracted fields.
    """

    job_title: str | None = Field(default=None, description="The role's job title.")
    department: str | None = Field(default=None, description="Team or department, if mentioned.")
    location: str | None = Field(default=None, description="Work location or 'Remote', if mentioned.")
    employment_type: str | None = Field(
        default=None, description="e.g. Full-time, Part-time, Contract, Internship."
    )
    min_years: float | None = Field(default=None, description="Minimum years of experience required.")
    max_years: float | None = Field(
        default=None, description="Maximum years of experience, if a range is given."
    )
    must_have_skills: list[str] = Field(
        default_factory=list, description="Explicitly required/mandatory skills or technologies."
    )
    good_to_have_skills: list[str] = Field(
        default_factory=list, description="Explicitly optional/preferred/nice-to-have skills."
    )
    key_responsibilities: list[str] = Field(
        default_factory=list, description="Short, individual bullet points of what the role does."
    )
    qualifications: str | None = Field(
        default=None, description="Education/certification/eligibility requirements, summarized."
    )


class JDUpdate(JDExtractedFields):
    """Recruiter edits from the review form. The frontend always sends the
    full form back, so a missing field means "clear it", not "leave as is" -
    fine for this POC's single review form.
    """


class JDResponse(JDExtractedFields):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    status: JDStatus
    raw_text: str | None = None
    edited_fields: dict[str, bool] = Field(default_factory=dict)
    version: int
    confirmed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class JDListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    job_title: str | None = None
    status: JDStatus
    version: int
    created_at: datetime
