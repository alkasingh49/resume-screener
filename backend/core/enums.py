"""Shared status/label enums.

Defined once here and imported by both db/models (SQLAlchemy columns) and
schemas (Pydantic models) so the two layers can never drift apart.
"""

from enum import Enum


class JDStatus(str, Enum):
    UPLOADED = "UPLOADED"
    PARSED = "PARSED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"


class ResumeStatus(str, Enum):
    PENDING = "PENDING"
    PARSING = "PARSING"
    SCORING = "SCORING"
    DONE = "DONE"
    FAILED = "FAILED"


class Fit(str, Enum):
    BEST = "BEST"
    MEDIUM = "MEDIUM"
    NO = "NO"


class ScreeningResultStatus(str, Enum):
    CURRENT = "CURRENT"
    STALE = "STALE"


class Difficulty(str, Enum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


class ExperienceSource(str, Enum):
    COMPUTED = "COMPUTED"
    LLM_FALLBACK = "LLM_FALLBACK"
