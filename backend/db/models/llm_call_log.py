"""One row per LLM call - backs the "log every LLM call, its provider, model,
token usage, and latency" non-functional requirement. Written by
backend/llm/wrapper.py on every call, in addition to the stdlib log line.
"""

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, TimestampMixin


class LLMCallLog(Base, TimestampMixin):
    __tablename__ = "llm_call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    operation: Mapped[str] = mapped_column(String(100))
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # loose reference (e.g. ref_type="job_description", ref_id=<jd.id>) rather
    # than a real FK - callers won't always have one (the CLI smoke test doesn't).
    ref_type: Mapped[str | None] = mapped_column(String(50))
    ref_id: Mapped[int | None] = mapped_column(Integer)
