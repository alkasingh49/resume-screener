"""Pydantic schemas for technical assessment generation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.core.enums import Difficulty


class AssessmentQuestion(BaseModel):
    """One question - see backend/prompts/generate_assessment.md.
    `expected_answer_points` is what makes the interviewer version different
    from the candidate-facing export, which strips this field.
    """

    question: str = Field(description="A clear, specific technical question - not yes/no.")
    skill_tag: str = Field(description="Which single skill this question tests.")
    difficulty: Difficulty = Field(description="EASY, MEDIUM, or HARD.")
    expected_answer_points: list[str] = Field(
        default_factory=list,
        description="2-4 bullet points of what a strong answer should cover, for the interviewer.",
    )


class AssessmentGeneratedFields(BaseModel):
    """What the LLM outputs when generating an assessment."""

    questions: list[AssessmentQuestion]


class AssessmentGenerateRequest(BaseModel):
    resume_id: int
    num_easy: int = Field(default=2, ge=0, le=10)
    num_medium: int = Field(default=2, ge=0, le=10)
    num_hard: int = Field(default=1, ge=0, le=10)


class AssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: int
    jd_id: int
    questions: list[AssessmentQuestion]
    created_at: datetime
