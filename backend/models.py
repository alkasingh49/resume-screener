"""Database tables. Three of them, on purpose.

A candidate IS a resume row here: everything the AI extracts (name, email,
phone, experience) and everything it scores (fit, rating, reason) lives on
the same row. There is no separate candidate or screening-result table,
because for this workflow there is never more than one of each per resume.
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Status(str, Enum):
    """Shared by JDs and resumes - the lifecycle is the same shape for both."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DONE = "DONE"
    FAILED = "FAILED"


class Fit(str, Enum):
    BEST = "BEST"
    MEDIUM = "MEDIUM"
    NO = "NO"


class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(500))
    raw_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default=Status.PENDING)
    error: Mapped[str | None] = mapped_column(Text)

    # Extracted by the LLM, editable by the recruiter.
    title: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    min_years: Mapped[float | None] = mapped_column(Float)
    max_years: Mapped[float | None] = mapped_column(Float)
    must_have_skills: Mapped[list] = mapped_column(JSON, default=list)
    good_to_have_skills: Mapped[list] = mapped_column(JSON, default=list)
    responsibilities: Mapped[list] = mapped_column(JSON, default=list)

    resumes: Mapped[list["Resume"]] = relationship(
        back_populates="jd", cascade="all, delete-orphan"
    )


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    jd_id: Mapped[int] = mapped_column(ForeignKey("job_descriptions.id"), index=True)

    filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(500))
    raw_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=Status.PENDING)
    error: Mapped[str | None] = mapped_column(Text)

    # --- Extracted by the AI ---
    name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    location: Mapped[str | None] = mapped_column(String(255))
    current_title: Mapped[str | None] = mapped_column(String(255))
    current_company: Mapped[str | None] = mapped_column(String(255))
    total_experience_years: Mapped[float | None] = mapped_column(Float)
    relevant_experience_years: Mapped[float | None] = mapped_column(Float)
    skills: Mapped[list] = mapped_column(JSON, default=list)

    # --- Scored by the AI ---
    skill_scores: Mapped[dict] = mapped_column(JSON, default=dict)  # {skill: 0-10}
    score: Mapped[int | None] = mapped_column(Integer)  # 0-100
    fit: Mapped[str | None] = mapped_column(String(10))  # Fit
    reason: Mapped[str | None] = mapped_column(Text)

    jd: Mapped["JobDescription"] = relationship(back_populates="resumes")
    assessments: Mapped[list["Assessment"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id"), index=True)

    # [{question, skill, difficulty, expected_answer}, ...]
    questions: Mapped[list] = mapped_column(JSON, default=list)

    resume: Mapped["Resume"] = relationship(back_populates="assessments")
