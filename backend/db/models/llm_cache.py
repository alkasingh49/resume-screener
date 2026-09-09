"""LLM response cache, keyed by a caller-supplied cache key (services build
it as file_hash + jd_id + model name, per the caching requirement) and
hashed here for a fixed-width lookup column. Backs
backend/llm/wrapper.py:run_with_resilience - replaces the file-based cache
used as a placeholder in Phase 1.
"""

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, TimestampMixin


class LLMCacheEntry(Base, TimestampMixin):
    __tablename__ = "llm_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    operation: Mapped[str | None] = mapped_column(String(100))
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
