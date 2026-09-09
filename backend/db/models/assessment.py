"""Generated technical assessment for one candidate against one JD.

`questions` holds the full interviewer version (question, skill_tag,
difficulty, expected_answer_points); the candidate-facing export strips
expected_answer_points at export time rather than being stored separately.
"""

from sqlalchemy import JSON, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin


class Assessment(Base, TimestampMixin):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False, index=True)
    jd_id: Mapped[int] = mapped_column(ForeignKey("job_descriptions.id"), nullable=False, index=True)

    questions: Mapped[list] = mapped_column(JSON, default=list)

    candidate: Mapped["Candidate"] = relationship(back_populates="assessments")
    job_description: Mapped["JobDescription"] = relationship(back_populates="assessments")
