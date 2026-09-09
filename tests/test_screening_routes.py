"""Tests for the screening results routes, including the results-table
endpoint the dashboard (Phase 8) renders from - built against a real temp DB
with directly-constructed JD/Resume/Candidate/ScreeningResult rows, no LLM
involved.
"""

import pytest
from fastapi.testclient import TestClient

from backend.core.enums import ExperienceSource, Fit, JDStatus, ResumeStatus, ScreeningResultStatus
from backend.db.models.candidate import Candidate
from backend.db.models.job_description import JobDescription
from backend.db.models.resume import Resume
from backend.db.models.screening_result import ScreeningResult
from backend.db.session import session_scope
from backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _db(isolated_db):
    pass


def _make_scored_candidate(
    *, jd_id: int, name: str, overall_rating: int, fit: Fit, result_status=ScreeningResultStatus.CURRENT
) -> int:
    with session_scope() as db:
        resume = Resume(
            jd_id=jd_id, filename=f"{name}.pdf", storage_path="x", file_size=1, status=ResumeStatus.DONE
        )
        db.add(resume)
        db.flush()

        candidate = Candidate(
            resume_id=resume.id,
            name=name,
            email=f"{name.lower()}@example.com",
            phone="123",
            skills=["Python", "SQL"],
            total_experience_years=5,
            total_experience_source=ExperienceSource.COMPUTED,
        )
        db.add(candidate)
        db.flush()

        db.add(
            ScreeningResult(
                candidate_id=candidate.id,
                jd_id=jd_id,
                jd_version=1,
                per_skill_scores={"Python": 8, "SQL": 6},
                overall_rating=overall_rating,
                relevant_experience_years=4,
                fit=fit,
                reason=f"Reason for {name}.",
                result_status=result_status,
            )
        )
        return resume.id


def _make_jd() -> int:
    with session_scope() as db:
        jd = JobDescription(filename="jd.pdf", storage_path="x", status=JDStatus.CONFIRMED, job_title="Engineer")
        db.add(jd)
        db.flush()
        return jd.id


def test_table_requires_existing_jd():
    assert client.get("/api/v1/screening/results/table?jd_id=9999").status_code == 404


def test_table_returns_joined_candidate_and_result_fields():
    jd_id = _make_jd()
    _make_scored_candidate(jd_id=jd_id, name="Ada", overall_rating=90, fit=Fit.BEST)

    rows = client.get(f"/api/v1/screening/results/table?jd_id={jd_id}").json()
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "Ada"
    assert row["email"] == "ada@example.com"
    assert row["overall_rating"] == 90
    assert row["fit"] == "BEST"
    assert row["per_skill_scores"] == {"Python": 8, "SQL": 6}
    assert row["skills"] == ["Python", "SQL"]
    assert row["reason"] == "Reason for Ada."


def test_table_is_sorted_by_rating_descending():
    jd_id = _make_jd()
    _make_scored_candidate(jd_id=jd_id, name="Low", overall_rating=40, fit=Fit.NO)
    _make_scored_candidate(jd_id=jd_id, name="High", overall_rating=95, fit=Fit.BEST)
    _make_scored_candidate(jd_id=jd_id, name="Mid", overall_rating=60, fit=Fit.MEDIUM)

    rows = client.get(f"/api/v1/screening/results/table?jd_id={jd_id}").json()
    assert [r["name"] for r in rows] == ["High", "Mid", "Low"]


def test_table_excludes_stale_results():
    jd_id = _make_jd()
    _make_scored_candidate(
        jd_id=jd_id, name="Stale", overall_rating=99, fit=Fit.BEST, result_status=ScreeningResultStatus.STALE
    )
    _make_scored_candidate(jd_id=jd_id, name="Fresh", overall_rating=50, fit=Fit.MEDIUM)

    rows = client.get(f"/api/v1/screening/results/table?jd_id={jd_id}").json()
    assert [r["name"] for r in rows] == ["Fresh"]


def test_table_empty_for_jd_with_no_results():
    jd_id = _make_jd()
    assert client.get(f"/api/v1/screening/results/table?jd_id={jd_id}").json() == []
