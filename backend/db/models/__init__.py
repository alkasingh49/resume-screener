"""Importing this module registers every model on Base.metadata - required
before `Base.metadata.create_all()` (see db/session.py:init_db) or before any
relationship() string forward-reference gets resolved.
"""

from backend.db.models.assessment import Assessment
from backend.db.models.candidate import Candidate
from backend.db.models.job_description import JobDescription
from backend.db.models.llm_call_log import LLMCallLog
from backend.db.models.llm_cache import LLMCacheEntry
from backend.db.models.resume import Resume
from backend.db.models.screening_result import ScreeningResult

__all__ = [
    "Assessment",
    "Candidate",
    "JobDescription",
    "LLMCallLog",
    "LLMCacheEntry",
    "Resume",
    "ScreeningResult",
]
