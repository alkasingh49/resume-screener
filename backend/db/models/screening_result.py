"""A candidate's score against one JD version. `jd_version` pins the result to
the JD snapshot it was scored against; when a confirmed JD is later edited,
existing rows get flipped to result_status=STALE rather than deleted or
silently left looking current - see backend/core/enums.ScreeningResultStatus.
"""

from sqlalchemy import JSON, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.enums import Fit, ScreeningResultStatus
from backend.db.base import Base, TimestampMixin


class ScreeningResult(Base, TimestampMixin):
    __tablename__ = "screening_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False, index=True)
    jd_id: Mapped[int] = mapped_column(ForeignKey("job_descriptions.id"), nullable=False, index=True)
    jd_version: Mapped[int] = mapped_column(Integer, nullable=False)

    per_skill_scores: Mapped[dict] = mapped_column(JSON, default=dict)  # {skill: 0-10}
    overall_rating: Mapped[int | None] = mapped_column(Integer)  # 0-100
    relevant_experience_years: Mapped[float | None] = mapped_column(Float)
    fit: Mapped[Fit | None] = mapped_column(
        Enum(Fit, native_enum=False, values_callable=lambda e: [m.value for m in e])
    )
    reason: Mapped[str | None] = mapped_column(Text)

    result_status: Mapped[ScreeningResultStatus] = mapped_column(
        Enum(ScreeningResultStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        default=ScreeningResultStatus.CURRENT,
        nullable=False,
    )
    model_name: Mapped[str | None] = mapped_column(String(100))

    candidate: Mapped["Candidate"] = relationship(back_populates="screening_results")
    job_description: Mapped["JobDescription"] = relationship(back_populates="screening_results")
