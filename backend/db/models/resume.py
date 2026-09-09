"""Resume upload table. See backend/core/enums.ResumeStatus for the per-file
status lifecycle the UI polls.
"""

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.enums import ResumeStatus
from backend.db.base import Base, TimestampMixin


class Resume(Base, TimestampMixin):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    jd_id: Mapped[int] = mapped_column(ForeignKey("job_descriptions.id"), nullable=False, index=True)

    filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(500))
    file_size: Mapped[int] = mapped_column(Integer)
    mime_type: Mapped[str | None] = mapped_column(String(100))
    file_hash: Mapped[str | None] = mapped_column(String(64), index=True)  # cache key input

    status: Mapped[ResumeStatus] = mapped_column(
        Enum(ResumeStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        default=ResumeStatus.PENDING,
        nullable=False,
    )
    raw_text: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)  # set when status=FAILED

    job_description: Mapped["JobDescription"] = relationship(back_populates="resumes")
    candidate: Mapped["Candidate | None"] = relationship(back_populates="resume", uselist=False)
