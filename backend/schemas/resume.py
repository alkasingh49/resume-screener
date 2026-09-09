"""Pydantic schemas for the resume upload flow. Deliberately separate from
the JD schemas - see backend/schemas/jd.py.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from backend.core.enums import ResumeStatus


class ResumeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    jd_id: int
    filename: str
    file_size: int
    mime_type: str | None = None
    status: ResumeStatus
    raw_text: str | None = None  # populated once processing has run at least once
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class ResumeUploadBatchResponse(BaseModel):
    """Summary + per-file results for one bulk upload call."""

    jd_id: int
    uploaded: int  # files stored and awaiting processing (status=PENDING)
    failed: int  # files rejected immediately (e.g. unsupported extension)
    resumes: list[ResumeResponse]
