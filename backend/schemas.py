"""Pydantic models: what the LLM must return, and what the API returns.

Keeping both in one file makes the mapping between them obvious - the
screening flow reads an `LLMScreening` and writes a `ResumeOut`.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# What we ask the LLM for (these become the structured-output schema)
# ---------------------------------------------------------------------------


class LLMJobDescription(BaseModel):
    """Fields pulled out of a raw job description."""

    title: str | None = Field(None, description="The job title")
    location: str | None = Field(None, description="Work location, or null if not stated")
    min_years: float | None = Field(None, description="Minimum years of experience required")
    max_years: float | None = Field(None, description="Maximum years of experience, or null")
    must_have_skills: list[str] = Field(default_factory=list, description="Required skills")
    good_to_have_skills: list[str] = Field(default_factory=list, description="Preferred skills")
    responsibilities: list[str] = Field(default_factory=list, description="Key responsibilities")


class SkillScore(BaseModel):
    """A list of these, rather than a dict, because every provider's
    structured output handles fixed-shape objects far more reliably than
    free-form dictionary keys."""

    skill: str = Field(description="A must-have skill from the job description")
    score: int = Field(ge=0, le=10, description="How well the resume evidences this skill, 0-10")


class LLMScreening(BaseModel):
    """Everything we need from one resume, in a single LLM call: the contact
    details, the experience maths, and the scoring."""

    name: str | None = Field(None, description="Candidate's full name")
    email: str | None = Field(None, description="Email address")
    phone: str | None = Field(None, description="Contact phone number, digits and + only")
    location: str | None = Field(None, description="Candidate's city/country")
    current_title: str | None = Field(None, description="Most recent job title")
    current_company: str | None = Field(None, description="Most recent employer")
    total_experience_years: float | None = Field(
        None, description="Total professional experience in years"
    )
    relevant_experience_years: float | None = Field(
        None, description="Years of experience relevant to THIS job description"
    )
    skills: list[str] = Field(default_factory=list, description="Skills found in the resume")
    skill_scores: list[SkillScore] = Field(
        default_factory=list, description="One entry per must-have skill in the job description"
    )
    score: int = Field(ge=0, le=100, description="Overall match rating, 0-100")
    reason: str = Field(description="2-3 sentences justifying the score, citing resume evidence")


class LLMQuestion(BaseModel):
    question: str = Field(description="The interview question")
    skill: str = Field(description="Which skill this question tests")
    difficulty: str = Field(description="One of: EASY, MEDIUM, HARD")
    expected_answer: str = Field(description="What a strong answer covers, for the interviewer")


class LLMQuestionSet(BaseModel):
    questions: list[LLMQuestion]


# ---------------------------------------------------------------------------
# What the API returns
# ---------------------------------------------------------------------------


class JDBrief(BaseModel):
    """Row in the job-description list."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    filename: str
    status: str
    title: str | None
    resume_count: int = 0


class JDOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    filename: str
    status: str
    error: str | None
    title: str | None
    location: str | None
    min_years: float | None
    max_years: float | None
    must_have_skills: list[str]
    good_to_have_skills: list[str]
    responsibilities: list[str]


class JDEdit(BaseModel):
    """Recruiter corrections to what the AI extracted."""

    title: str | None = None
    location: str | None = None
    min_years: float | None = None
    max_years: float | None = None
    must_have_skills: list[str] = Field(default_factory=list)
    good_to_have_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)


class ResumeOut(BaseModel):
    """One row of the screening results table."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    jd_id: int
    filename: str
    status: str
    error: str | None

    name: str | None
    email: str | None
    phone: str | None
    location: str | None
    current_title: str | None
    current_company: str | None
    total_experience_years: float | None
    relevant_experience_years: float | None
    skills: list[str]

    skill_scores: dict[str, int]
    score: int | None
    fit: str | None
    reason: str | None


class UploadSummary(BaseModel):
    jd_id: int
    uploaded: int
    rejected: int
    resumes: list[ResumeOut]


class AssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    resume_id: int
    questions: list[dict]
