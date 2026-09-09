"""JD table. See backend/core/enums.JDStatus for the status lifecycle.

`version` increments whenever a CONFIRMED JD is edited again; existing
screening_results keep the jd_version they were scored against, so an edit
can flip old results STALE instead of silently keeping them.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.enums import JDStatus
from backend.db.base import Base, TimestampMixin


class JobDescription(Base, TimestampMixin):
    __tablename__ = "job_descriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(500))
    raw_text: Mapped[str | None] = mapped_column(Text)

    status: Mapped[JDStatus] = mapped_column(
        Enum(JDStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        default=JDStatus.UPLOADED,
        nullable=False,
    )

    job_title: Mapped[str | None] = mapped_column(String(255))
    department: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    employment_type: Mapped[str | None] = mapped_column(String(100))
    min_years: Mapped[float | None] = mapped_column(Float)
    max_years: Mapped[float | None] = mapped_column(Float)
    must_have_skills: Mapped[list] = mapped_column(JSON, default=list)
    good_to_have_skills: Mapped[list] = mapped_column(JSON, default=list)
    key_responsibilities: Mapped[list] = mapped_column(JSON, default=list)
    qualifications: Mapped[str | None] = mapped_column(Text)

    # field name -> True if the recruiter edited the LLM's extraction, so we
    # can see what the LLM got wrong.
    edited_fields: Mapped[dict] = mapped_column(JSON, default=dict)

    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_message: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)  # soft delete

    resumes: Mapped[list["Resume"]] = relationship(back_populates="job_description")
    screening_results: Mapped[list["ScreeningResult"]] = relationship(back_populates="job_description")
    assessments: Mapped[list["Assessment"]] = relationship(back_populates="job_description")
