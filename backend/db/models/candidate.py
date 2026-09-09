"""Extracted candidate profile - one row per resume (1:1)."""

from sqlalchemy import JSON, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.enums import ExperienceSource
from backend.db.base import Base, TimestampMixin


class Candidate(Base, TimestampMixin):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id"), unique=True, nullable=False)

    name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    location: Mapped[str | None] = mapped_column(String(255))
    current_title: Mapped[str | None] = mapped_column(String(255))
    current_company: Mapped[str | None] = mapped_column(String(255))

    total_experience_years: Mapped[float | None] = mapped_column(Float)
    # COMPUTED = derived from work_history dates; LLM_FALLBACK = date math wasn't possible.
    total_experience_source: Mapped[ExperienceSource | None] = mapped_column(
        Enum(ExperienceSource, native_enum=False, values_callable=lambda e: [m.value for m in e])
    )

    skills: Mapped[list] = mapped_column(JSON, default=list)
    education: Mapped[list] = mapped_column(JSON, default=list)
    work_history: Mapped[list] = mapped_column(JSON, default=list)
    certifications: Mapped[list] = mapped_column(JSON, default=list)

    resume: Mapped["Resume"] = relationship(back_populates="candidate")
    screening_results: Mapped[list["ScreeningResult"]] = relationship(back_populates="candidate")
    assessments: Mapped[list["Assessment"]] = relationship(back_populates="candidate")
