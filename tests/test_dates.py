"""Unit tests for the total-experience date math - pure logic, no mocking."""

from datetime import date

from backend.utils.dates import compute_total_experience_years

TODAY = date(2026, 9, 8)


def test_single_role_computed_in_years():
    work_history = [{"start_date": "Jan 2020", "end_date": "Dec 2021"}]
    # Jan 2020 through Dec 2021 inclusive = 24 months = 2.0 years
    assert compute_total_experience_years(work_history, today=TODAY) == 2.0


def test_multiple_non_overlapping_roles_are_summed():
    work_history = [
        {"start_date": "Jan 2018", "end_date": "Dec 2019"},  # 24 months
        {"start_date": "Jan 2020", "end_date": "Jun 2020"},  # 6 months
    ]
    assert compute_total_experience_years(work_history, today=TODAY) == 2.5


def test_overlapping_concurrent_roles_are_not_double_counted():
    work_history = [
        {"start_date": "Jan 2020", "end_date": "Dec 2021"},
        {"start_date": "Jun 2020", "end_date": "Jun 2022"},  # overlaps the first
    ]
    # merged range: Jan 2020 - Jun 2022 inclusive = 30 months = 2.5 years
    assert compute_total_experience_years(work_history, today=TODAY) == 2.5


def test_ongoing_role_uses_today():
    work_history = [{"start_date": "Jan 2025", "end_date": "Present"}]
    # Jan 2025 through Sep 2026 inclusive = 21 months = 1.75 -> rounds to 1.8
    assert compute_total_experience_years(work_history, today=TODAY) == 1.8


def test_missing_end_date_treated_as_ongoing():
    work_history = [{"start_date": "Jan 2025"}]
    assert compute_total_experience_years(work_history, today=TODAY) == 1.8


def test_bare_year_defaults_to_january():
    work_history = [{"start_date": "2020", "end_date": "2020"}]
    assert compute_total_experience_years(work_history, today=TODAY) == round(1 / 12, 1)


def test_various_date_formats_all_parse():
    formats = ["2020-01", "2020/01", "01-2020", "01/2020", "January 2020", "Jan 2020", "Jan, 2020"]
    for fmt in formats:
        work_history = [{"start_date": fmt, "end_date": "Dec 2020"}]
        result = compute_total_experience_years(work_history, today=TODAY)
        assert result is not None, f"failed to parse start_date format: {fmt!r}"


def test_entries_with_unparseable_dates_are_skipped_not_fatal():
    work_history = [
        {"start_date": "sometime last year", "end_date": "recently"},  # unparseable
        {"start_date": "Jan 2020", "end_date": "Dec 2020"},  # parseable, 12 months
    ]
    assert compute_total_experience_years(work_history, today=TODAY) == 1.0


def test_all_unparseable_returns_none():
    work_history = [{"start_date": "a long time ago", "end_date": "later"}]
    assert compute_total_experience_years(work_history, today=TODAY) is None


def test_empty_work_history_returns_none():
    assert compute_total_experience_years([], today=TODAY) is None
    assert compute_total_experience_years(None, today=TODAY) is None


def test_end_before_start_is_skipped_not_negative():
    work_history = [{"start_date": "Jan 2022", "end_date": "Jan 2020"}]
    assert compute_total_experience_years(work_history, today=TODAY) is None


def test_non_dict_entries_are_ignored():
    work_history = ["not a dict", {"start_date": "Jan 2020", "end_date": "Dec 2020"}]
    assert compute_total_experience_years(work_history, today=TODAY) == 1.0
