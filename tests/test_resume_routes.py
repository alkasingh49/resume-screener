"""Resume bulk-upload API tests against a real temp DB - upload itself
involves no LLM calls, but it does queue a FastAPI BackgroundTasks run of
the full parse+score pipeline (backend/services/pipeline.py) for the newly-
PENDING resumes, which TestClient runs synchronously before returning the
response. That's covered in tests/test_pipeline.py; here it's mocked out so
these tests stay scoped to upload/storage behaviour only.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.core.enums import JDStatus, ResumeStatus
from backend.db.models.job_description import JobDescription
from backend.db.session import session_scope
from backend.main import app

FIXTURES = Path(__file__).parent / "fixtures"
client = TestClient(app)


@pytest.fixture(autouse=True)
def _db(isolated_db, monkeypatch):
    monkeypatch.setattr("backend.api.v1.routes.resumes.pipeline.run_pipeline_for_jd", lambda *a, **k: 0)


def _make_jd(status: JDStatus = JDStatus.CONFIRMED) -> int:
    with session_scope() as db:
        jd = JobDescription(
            filename="jd.pdf",
            storage_path="x",
            status=status,
            job_title="Backend Engineer",
            must_have_skills=["Python"],
        )
        db.add(jd)
        db.flush()
        return jd.id


def _pdf_bytes() -> bytes:
    return (FIXTURES / "sample_jd.pdf").read_bytes()


def test_upload_requires_confirmed_jd():
    jd_id = _make_jd(status=JDStatus.PARSED)  # not confirmed
    response = client.post(
        f"/api/v1/resumes/upload?jd_id={jd_id}",
        files=[("files", ("r.pdf", _pdf_bytes(), "application/pdf"))],
    )
    assert response.status_code == 400


def test_upload_requires_existing_jd():
    response = client.post(
        "/api/v1/resumes/upload?jd_id=9999",
        files=[("files", ("r.pdf", _pdf_bytes(), "application/pdf"))],
    )
    assert response.status_code == 404


def test_bulk_upload_mixed_good_and_bad_files_never_aborts_batch():
    jd_id = _make_jd()
    response = client.post(
        f"/api/v1/resumes/upload?jd_id={jd_id}",
        files=[
            ("files", ("good1.pdf", _pdf_bytes(), "application/pdf")),
            ("files", ("bad.doc", b"legacy binary content", "application/msword")),
            ("files", ("good2.txt", b"Name: Someone\nSkills: Python", "text/plain")),
        ],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["jd_id"] == jd_id
    assert body["uploaded"] == 2
    assert body["failed"] == 1
    assert len(body["resumes"]) == 3

    statuses = {r["filename"]: r["status"] for r in body["resumes"]}
    assert statuses["good1.pdf"] == ResumeStatus.PENDING.value
    assert statuses["good2.txt"] == ResumeStatus.PENDING.value
    assert statuses["bad.doc"] == ResumeStatus.FAILED.value

    bad = next(r for r in body["resumes"] if r["filename"] == "bad.doc")
    assert "Unsupported file type" in bad["error_message"]
    # even the rejected file's raw bytes were stored
    assert bad["file_size"] == len(b"legacy binary content")


def test_uploaded_files_are_saved_with_size_mime_and_hash():
    jd_id = _make_jd()
    content = _pdf_bytes()
    response = client.post(
        f"/api/v1/resumes/upload?jd_id={jd_id}",
        files=[("files", ("resume.pdf", content, "application/pdf"))],
    )
    resume = response.json()["resumes"][0]
    assert resume["file_size"] == len(content)
    assert resume["mime_type"] == "application/pdf"
    assert resume["status"] == ResumeStatus.PENDING.value


def test_list_resumes_for_jd():
    jd_id = _make_jd()
    other_jd_id = _make_jd()
    client.post(
        f"/api/v1/resumes/upload?jd_id={jd_id}",
        files=[("files", ("a.pdf", _pdf_bytes(), "application/pdf"))],
    )
    client.post(
        f"/api/v1/resumes/upload?jd_id={other_jd_id}",
        files=[("files", ("b.pdf", _pdf_bytes(), "application/pdf"))],
    )

    listed = client.get(f"/api/v1/resumes?jd_id={jd_id}").json()
    assert len(listed) == 1
    assert listed[0]["filename"] == "a.pdf"


def test_list_resumes_requires_existing_jd():
    assert client.get("/api/v1/resumes?jd_id=9999").status_code == 404


def test_get_single_resume():
    jd_id = _make_jd()
    uploaded = client.post(
        f"/api/v1/resumes/upload?jd_id={jd_id}",
        files=[("files", ("a.pdf", _pdf_bytes(), "application/pdf"))],
    ).json()["resumes"][0]

    response = client.get(f"/api/v1/resumes/{uploaded['id']}")
    assert response.status_code == 200
    assert response.json()["filename"] == "a.pdf"


def test_get_missing_resume_404():
    assert client.get("/api/v1/resumes/9999").status_code == 404
