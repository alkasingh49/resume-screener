"""Date parsing + total-experience computation for candidate work history.

Resume dates come out of the LLM as loosely-formatted strings ("Jan 2020",
"2020-01", "2020", "Present"/"Current" for an ongoing role) - this module
turns those into (year, month) pairs and sums non-overlapping work_history
ranges into a total years figure, merging overlapping/concurrent roles so
they aren't double-counted. Pure date math; no candidate/JD business logic.
"""

import re
from datetime import date

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_ONGOING_MARKERS = {"present", "current", "currently", "ongoing", "now", "till date", "to date"}


def _parse_month_year(text: str | None) -> tuple[int, int] | None:
    """Best-effort parse of a single date-ish string into (year, month).
    Returns None if it can't be confidently parsed.
    """
    if not text:
        return None
    cleaned = text.strip().lower()
    if not cleaned:
        return None

    m = re.match(r"^(\d{4})[-/](\d{1,2})$", cleaned)  # "2020-01", "2020/01"
    if m:
        return int(m.group(1)), int(m.group(2))

    m = re.match(r"^(\d{1,2})[-/](\d{4})$", cleaned)  # "01-2020", "01/2020"
    if m:
        return int(m.group(2)), int(m.group(1))

    m = re.match(r"^([a-zA-Z]+)\.?,?\s+(\d{4})$", cleaned)  # "January 2020", "Jan 2020"
    if m and m.group(1) in _MONTHS:
        return int(m.group(2)), _MONTHS[m.group(1)]

    m = re.match(r"^(\d{4})$", cleaned)  # bare year "2020" - default to January
    if m:
        return int(m.group(1)), 1

    return None


def _parse_end(text: str | None, today: date) -> tuple[int, int] | None:
    if text is None:
        return today.year, today.month
    cleaned = text.strip().lower()
    if not cleaned or cleaned in _ONGOING_MARKERS:
        return today.year, today.month
    return _parse_month_year(text)


def compute_total_experience_years(
    work_history: list[dict], *, today: date | None = None
) -> float | None:
    """Sum non-overlapping ranges from `work_history` entries (each expected
    to have "start_date" and optionally "end_date") into a total years
    figure, merging overlapping/concurrent roles so they aren't double-
    counted. Returns None if no entry has a parseable start date - callers
    should fall back to the LLM's own total_experience_years estimate.
    """
    today = today or date.today()
    intervals: list[tuple[int, int]] = []  # (start_month_index, end_month_index)

    for entry in work_history or []:
        if not isinstance(entry, dict):
            continue
        start = _parse_month_year(entry.get("start_date"))
        if start is None:
            continue
        end = _parse_end(entry.get("end_date"), today)
        if end is None:
            continue

        start_idx = start[0] * 12 + start[1]
        end_idx = end[0] * 12 + end[1]
        if end_idx < start_idx:
            continue  # malformed range - skip rather than produce a negative
        intervals.append((start_idx, end_idx))

    if not intervals:
        return None

    intervals.sort()
    merged: list[list[int]] = []
    for start_idx, end_idx in intervals:
        if merged and start_idx <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end_idx)
        else:
            merged.append([start_idx, end_idx])

    total_months = sum(end_idx - start_idx + 1 for start_idx, end_idx in merged)
    return round(total_months / 12, 1)
