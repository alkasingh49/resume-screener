"""Tests for backend/services/pipeline.py and the routes that trigger it:
automatic background processing on upload, the single-resume manual
retry, and the batch manual retry. Profile extraction and scoring are
mocked at their respective boundaries; RAG indexing runs for real against a
local Chroma collection with the keyword-based fake embedding.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.core.enums import JDStatus, ResumeStatus
from backend.db.models.job_description import JobDescription
from backend.db.session import session_scope
from backend.main import app
from backend.schemas.candidate import CandidateExtractedFields
from backend.schemas.screening import ScoringExtractedFields
from backend.services import vectorstore
from tests.test_vectorstore import KeywordEmbeddings

FIXTURES_DOCX = (Path(__file__).parent / "fixtures" / "sample_resume.docx").read_bytes()

client = TestClient(app)


@pytest.fixture(autouse=True)
def _db_and_fakes(isolated_db, monkeypatch):
    monkeypatch.setattr(vectorstore, "get_embeddings", lambda: KeywordEmbeddings())


def _mock_extract(monkeypatch, fields: CandidateExtractedFields | None = None):
    monkeypatch.setattr(
        "backend.services.resume.profile.extract_candidate_fields",
        lambda resume: fields or CandidateExtractedFields(name="Ada Lovelace", skills=["Python"]),
    )


def _mock_score(monkeypatch, fields: ScoringExtractedFields | None = None):
    monkeypatch.setattr(
        "backend.services.scoring._score_via_llm",
        lambda *a, **k: fields
        or ScoringExtractedFields(
            per_skill_scores={"Python": 8}, overall_rating=80, relevant_experience_years=3.0, reason="Solid fit."
        ),
    )


def _make_confirmed_jd() -> int:
    with session_scope() as db:
        jd = JobDescription(
            filename="jd.pdf",
            storage_path="x",
            status=JDStatus.CONFIRMED,
            job_title="Backend Engineer",
            must_have_skills=["Python"],
        )
        db.add(jd)
        db.flush()
        return jd.id


def test_upload_automatically_runs_the_pipeline_to_done(monkeypatch):
    """TestClient runs BackgroundTasks synchronously, so by the time
    client.post() returns, the newly-uploaded resume should already be DONE.
    """
    _mock_extract(monkeypatch)
    _mock_score(monkeypatch)

    jd_id = _make_confirmed_jd()
    client.post(
        f"/api/v1/resumes/upload?jd_id={jd_id}", files=[("files", ("r.docx", FIXTURES_DOCX, "application/octet-stream"))]
    )

    resumes = client.get(f"/api/v1/resumes?jd_id={jd_id}").json()
    assert resumes[0]["status"] == ResumeStatus.DONE.value

    result = client.get(f"/api/v1/screening/results/by-resume/{resumes[0]['id']}").json()
    assert result["overall_rating"] == 80
    assert result["fit"] == "BEST"


def test_upload_pipeline_failure_when_extraction_fails_leaves_resume_failed(monkeypatch):
    def _raise(resume):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr("backend.services.resume.profile.extract_candidate_fields", _raise)

    jd_id = _make_confirmed_jd()
    client.post(
        f"/api/v1/resumes/upload?jd_id={jd_id}", files=[("files", ("r.docx", FIXTURES_DOCX, "application/octet-stream"))]
    )

    resumes = client.get(f"/api/v1/resumes?jd_id={jd_id}").json()
    assert resumes[0]["status"] == ResumeStatus.FAILED.value
    assert "LLM unavailable" in resumes[0]["error_message"]


def test_process_endpoint_requires_existing_resume():
    assert client.post("/api/v1/resumes/9999/process").status_code == 404


def test_process_endpoint_runs_parse_and_score_and_rejects_double_processing(monkeypatch):
    _mock_extract(monkeypatch)
    _mock_score(monkeypatch)

    jd_id = _make_confirmed_jd()
    # mock the auto-trigger away so we control the single call explicitly
    import backend.api.v1.routes.resumes as resumes_route

    monkeypatch.setattr(resumes_route.pipeline, "run_pipeline_for_jd", lambda *a, **k: 0)

    upload = client.post(
        f"/api/v1/resumes/upload?jd_id={jd_id}", files=[("files", ("r.docx", FIXTURES_DOCX, "application/octet-stream"))]
    )
    resume_id = upload.json()["resumes"][0]["id"]
    assert upload.json()["resumes"][0]["status"] == ResumeStatus.PENDING.value  # auto-trigger was disabled

    first = client.post(f"/api/v1/resumes/{resume_id}/process")
    assert first.json()["status"] == ResumeStatus.DONE.value

    second = client.post(f"/api/v1/resumes/{resume_id}/process")
    assert second.status_code == 400


def test_batch_pipeline_retry_endpoint_processes_pending_and_failed(monkeypatch):
    import backend.api.v1.routes.resumes as resumes_route

    real_run_pipeline_for_jd = resumes_route.pipeline.run_pipeline_for_jd
    monkeypatch.setattr(resumes_route.pipeline, "run_pipeline_for_jd", lambda *a, **k: 0)  # disable auto-trigger for upload

    jd_id = _make_confirmed_jd()
    client.post(
        f"/api/v1/resumes/upload?jd_id={jd_id}",
        files=[
            ("files", ("a.docx", FIXTURES_DOCX, "application/octet-stream")),
            ("files", ("bad.doc", b"legacy", "application/msword")),  # immediately FAILED at upload
        ],
    )

    # restore the real pipeline for the manual retry call below
    monkeypatch.setattr(resumes_route.pipeline, "run_pipeline_for_jd", real_run_pipeline_for_jd)
    _mock_extract(monkeypatch)
    _mock_score(monkeypatch)
    response = client.post(f"/api/v1/resumes/pipeline/run?jd_id={jd_id}")
    assert response.status_code == 200
    assert response.json()["queued"] == 2  # 1 PENDING + 1 FAILED (include_failed=True)

    resumes = client.get(f"/api/v1/resumes?jd_id={jd_id}").json()
    statuses = {r["filename"]: r["status"] for r in resumes}
    assert statuses["a.docx"] == ResumeStatus.DONE.value
    assert statuses["bad.doc"] == ResumeStatus.FAILED.value  # still unsupported, retried and failed the same way


def test_batch_pipeline_retry_requires_existing_jd():
    assert client.post("/api/v1/resumes/pipeline/run?jd_id=9999").status_code == 404


def test_scoring_failure_after_successful_parsing_leaves_resume_failed_not_scoring(monkeypatch):
    _mock_extract(monkeypatch)

    def _raise(*a, **k):
        raise RuntimeError("scoring model unavailable")

    monkeypatch.setattr("backend.services.scoring._score_via_llm", _raise)

    jd_id = _make_confirmed_jd()
    client.post(
        f"/api/v1/resumes/upload?jd_id={jd_id}", files=[("files", ("r.docx", FIXTURES_DOCX, "application/octet-stream"))]
    )

    resumes = client.get(f"/api/v1/resumes?jd_id={jd_id}").json()
    assert resumes[0]["status"] == ResumeStatus.FAILED.value
    assert "scoring model unavailable" in resumes[0]["error_message"]


def test_scoring_result_is_hidden_if_jd_is_no_longer_confirmed(monkeypatch):
    """Guards against a race where a JD gets un-confirmed (not currently
    possible via the API, but the pipeline checks defensively) between a
    resume reaching SCORING and the scoring step actually running.
    """
    _mock_extract(monkeypatch)
    _mock_score(monkeypatch)

    jd_id = _make_confirmed_jd()
    import backend.api.v1.routes.resumes as resumes_route

    monkeypatch.setattr(resumes_route.pipeline, "run_pipeline_for_jd", lambda *a, **k: 0)
    upload = client.post(
        f"/api/v1/resumes/upload?jd_id={jd_id}", files=[("files", ("r.docx", FIXTURES_DOCX, "application/octet-stream"))]
    )
    resume_id = upload.json()["resumes"][0]["id"]

    with session_scope() as db:
        jd = db.get(JobDescription, jd_id)
        jd.status = JDStatus.NEEDS_REVIEW  # simulate JD no longer confirmed

    response = client.post(f"/api/v1/resumes/{resume_id}/process")
    body = response.json()
    assert body["status"] == ResumeStatus.FAILED.value
    assert "no longer confirmed" in body["error_message"]
