"""JD API tests against a real temp DB and real text extraction (the
sample_jd.pdf fixture has native text, no OCR needed) - only the LLM call
itself is mocked, since we don't have a real API key in CI/this sandbox.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.core.enums import Fit, JDStatus, ResumeStatus, ScreeningResultStatus
from backend.db.models.candidate import Candidate
from backend.db.models.resume import Resume
from backend.db.models.screening_result import ScreeningResult
from backend.db.session import session_scope
from backend.main import app
from backend.schemas.jd import JDExtractedFields

FIXTURES = Path(__file__).parent / "fixtures"
client = TestClient(app)


@pytest.fixture(autouse=True)
def _db(isolated_db):
    pass


def _mock_extract(monkeypatch, fields: JDExtractedFields):
    monkeypatch.setattr("backend.api.v1.routes.jd.extract_jd_fields", lambda jd: fields)


def _complete_fields(**overrides) -> JDExtractedFields:
    base = dict(
        job_title="Backend Engineer",
        department="Engineering",
        location="Remote",
        employment_type="Full-time",
        min_years=3,
        max_years=6,
        must_have_skills=["Python", "SQL"],
        good_to_have_skills=["Kubernetes"],
        key_responsibilities=["Build APIs", "Own data models"],
        qualifications="BS in CS or equivalent experience.",
    )
    base.update(overrides)
    return JDExtractedFields(**base)


def _upload(filename: str = "sample_jd.pdf", content: bytes | None = None):
    content = content if content is not None else (FIXTURES / "sample_jd.pdf").read_bytes()
    return client.post(
        "/api/v1/jds/upload", files={"file": (filename, content, "application/pdf")}
    )


def test_upload_with_complete_fields_is_parsed(monkeypatch):
    _mock_extract(monkeypatch, _complete_fields())
    response = _upload()
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == JDStatus.PARSED.value
    assert body["job_title"] == "Backend Engineer"
    assert body["must_have_skills"] == ["Python", "SQL"]
    assert "Backend Engineer" in body["raw_text"]  # real text extraction ran
    assert body["edited_fields"] == {}


def test_upload_with_incomplete_fields_needs_review(monkeypatch):
    _mock_extract(monkeypatch, _complete_fields(job_title=None))
    response = _upload()
    assert response.json()["status"] == JDStatus.NEEDS_REVIEW.value


def test_upload_unsupported_extension_is_marked_failed_not_500(monkeypatch):
    _mock_extract(monkeypatch, _complete_fields())  # should never be reached
    response = _upload(filename="resume.doc", content=b"legacy binary doc content")
    assert response.status_code == 200  # still a normal response, not a 5xx
    body = response.json()
    assert body["status"] == JDStatus.FAILED.value
    assert "not supported" in body["error_message"]


def test_list_and_get(monkeypatch):
    _mock_extract(monkeypatch, _complete_fields())
    created = _upload().json()

    listed = client.get("/api/v1/jds").json()
    assert any(item["id"] == created["id"] for item in listed)

    fetched = client.get(f"/api/v1/jds/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["job_title"] == "Backend Engineer"


def test_get_missing_jd_404():
    assert client.get("/api/v1/jds/9999").status_code == 404


def test_update_tracks_edited_fields(monkeypatch):
    _mock_extract(monkeypatch, _complete_fields())
    jd_id = _upload().json()["id"]

    payload = _complete_fields(job_title="Senior Backend Engineer").model_dump()
    response = client.put(f"/api/v1/jds/{jd_id}", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["job_title"] == "Senior Backend Engineer"
    assert body["edited_fields"]["job_title"] is True
    assert "department" not in body["edited_fields"]  # unchanged field, untouched


def test_confirm_requires_job_title_and_must_have_skills(monkeypatch):
    _mock_extract(monkeypatch, _complete_fields(job_title=None))
    jd_id = _upload().json()["id"]

    response = client.post(f"/api/v1/jds/{jd_id}/confirm")
    assert response.status_code == 400


def test_confirm_success(monkeypatch):
    _mock_extract(monkeypatch, _complete_fields())
    jd_id = _upload().json()["id"]

    response = client.post(f"/api/v1/jds/{jd_id}/confirm")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == JDStatus.CONFIRMED.value
    assert body["confirmed_at"] is not None

    # confirming again is rejected
    assert client.post(f"/api/v1/jds/{jd_id}/confirm").status_code == 400


def test_editing_a_confirmed_jd_bumps_version_and_marks_results_stale(monkeypatch):
    _mock_extract(monkeypatch, _complete_fields())
    jd_id = _upload().json()["id"]
    client.post(f"/api/v1/jds/{jd_id}/confirm")

    # FKs are enforced (PRAGMA foreign_keys=ON) - build a real resume/candidate
    # chain rather than a bare candidate_id.
    with session_scope() as db:
        resume = Resume(
            jd_id=jd_id,
            filename="c.pdf",
            storage_path="x",
            file_size=1,
            status=ResumeStatus.DONE,
        )
        db.add(resume)
        db.flush()
        candidate = Candidate(resume_id=resume.id, name="Test Candidate")
        db.add(candidate)
        db.flush()
        db.add(
            ScreeningResult(
                candidate_id=candidate.id,
                jd_id=jd_id,
                jd_version=1,
                fit=Fit.BEST,
                result_status=ScreeningResultStatus.CURRENT,
            )
        )

    payload = _complete_fields(job_title="Staff Backend Engineer").model_dump()
    response = client.put(f"/api/v1/jds/{jd_id}", json=payload)
    assert response.status_code == 200
    assert response.json()["version"] == 2
    assert response.json()["status"] == JDStatus.CONFIRMED.value  # stays usable

    with session_scope() as db:
        result = db.query(ScreeningResult).filter_by(jd_id=jd_id).one()
        assert result.result_status == ScreeningResultStatus.STALE


def test_reparse_disallowed_once_confirmed(monkeypatch):
    _mock_extract(monkeypatch, _complete_fields())
    jd_id = _upload().json()["id"]
    client.post(f"/api/v1/jds/{jd_id}/confirm")

    response = client.post(f"/api/v1/jds/{jd_id}/reparse")
    assert response.status_code == 400


def test_reparse_reruns_extraction(monkeypatch):
    _mock_extract(monkeypatch, _complete_fields(job_title="First Pass"))
    jd_id = _upload().json()["id"]

    _mock_extract(monkeypatch, _complete_fields(job_title="Second Pass"))
    response = client.post(f"/api/v1/jds/{jd_id}/reparse")
    assert response.json()["job_title"] == "Second Pass"


def test_soft_delete_excludes_from_list_and_get(monkeypatch):
    _mock_extract(monkeypatch, _complete_fields())
    jd_id = _upload().json()["id"]

    assert client.delete(f"/api/v1/jds/{jd_id}").status_code == 204
    assert client.get(f"/api/v1/jds/{jd_id}").status_code == 404
    assert all(item["id"] != jd_id for item in client.get("/api/v1/jds").json())
