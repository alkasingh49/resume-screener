"""Candidate profile extraction tests (Phase 5) against a real temp DB and
real text extraction (sample_resume.docx has native text). Calls
`profile.process_resume()` directly rather than through
`POST /resumes/{id}/process`, since that route now runs the full
parse+score pipeline (Phase 7) - see tests/test_pipeline.py for that. Only
the LLM extraction call and the RAG indexing step are mocked here.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.core.enums import ExperienceSource, JDStatus, ResumeStatus
from backend.db.models.job_description import JobDescription
from backend.db.session import session_scope
from backend.main import app
from backend.schemas.candidate import CandidateExtractedFields, WorkHistoryEntry
from backend.services.resume import profile, storage as resume_storage

FIXTURES = Path(__file__).parent / "fixtures"
client = TestClient(app)


@pytest.fixture(autouse=True)
def _db(isolated_db, monkeypatch):
    monkeypatch.setattr("backend.services.resume.profile.vectorstore.index_resume", lambda *a, **k: 0)
    # upload() queues the full pipeline as a background task - not what
    # these tests are exercising, so keep it inert here.
    monkeypatch.setattr("backend.api.v1.routes.resumes.pipeline.run_pipeline_for_jd", lambda *a, **k: 0)


def _mock_extract(monkeypatch, fields: CandidateExtractedFields):
    monkeypatch.setattr("backend.services.resume.profile.extract_candidate_fields", lambda resume: fields)


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


def _upload_one(jd_id: int, filename: str, content: bytes, content_type: str) -> int:
    response = client.post(
        f"/api/v1/resumes/upload?jd_id={jd_id}", files=[("files", (filename, content, content_type))]
    )
    return response.json()["resumes"][0]["id"]


def _docx_bytes() -> bytes:
    return (FIXTURES / "sample_resume.docx").read_bytes()


def _process(resume_id: int) -> str:
    """Run profile.process_resume() directly against a fresh session and
    return the resulting status (mirrors what the /process route does for
    just this one step)."""
    with session_scope() as db:
        resume = resume_storage.get_resume(db, resume_id)
        profile.process_resume(db, resume)
        return resume.status.value


def test_process_computes_experience_from_parseable_work_history(monkeypatch):
    fields = CandidateExtractedFields(
        name="Ada Lovelace",
        email="ada@example.com",
        current_title="Backend Engineer",
        total_experience_years=99,  # deliberately wrong - COMPUTED should win, not this
        work_history=[
            WorkHistoryEntry(title="Engineer II", company="Acme", start_date="Jan 2018", end_date="Dec 2019"),
            WorkHistoryEntry(title="Engineer I", company="Acme", start_date="Jan 2020", end_date="Jun 2020"),
        ],
    )
    _mock_extract(monkeypatch, fields)

    jd_id = _make_confirmed_jd()
    resume_id = _upload_one(jd_id, "r.docx", _docx_bytes(), "application/octet-stream")

    assert _process(resume_id) == ResumeStatus.SCORING.value

    candidate = client.get(f"/api/v1/resumes/{resume_id}/candidate").json()
    assert candidate["name"] == "Ada Lovelace"
    assert candidate["total_experience_years"] == 2.5  # 24 + 6 months, computed - not the LLM's 99
    assert candidate["total_experience_source"] == ExperienceSource.COMPUTED.value


def test_process_falls_back_to_llm_estimate_when_dates_unparseable(monkeypatch):
    fields = CandidateExtractedFields(
        name="Grace Hopper",
        total_experience_years=7.5,
        work_history=[
            WorkHistoryEntry(title="Engineer", company="Navy", start_date="a while back", end_date="recently")
        ],
    )
    _mock_extract(monkeypatch, fields)

    jd_id = _make_confirmed_jd()
    resume_id = _upload_one(jd_id, "r.docx", _docx_bytes(), "application/octet-stream")
    _process(resume_id)

    candidate = client.get(f"/api/v1/resumes/{resume_id}/candidate").json()
    assert candidate["total_experience_years"] == 7.5
    assert candidate["total_experience_source"] == ExperienceSource.LLM_FALLBACK.value


def test_process_stores_skills_education_and_certifications(monkeypatch):
    fields = CandidateExtractedFields(
        name="Ada Lovelace",
        skills=["Python", "SQL"],
        certifications=["AWS Certified Developer"],
    )
    _mock_extract(monkeypatch, fields)

    jd_id = _make_confirmed_jd()
    resume_id = _upload_one(jd_id, "r.docx", _docx_bytes(), "application/octet-stream")
    _process(resume_id)

    candidate = client.get(f"/api/v1/resumes/{resume_id}/candidate").json()
    assert candidate["skills"] == ["Python", "SQL"]
    assert candidate["certifications"] == ["AWS Certified Developer"]


def test_process_failure_is_captured_not_raised():
    # a resume that failed at upload (unsupported extension) has no raw_text
    # and its storage_path points at a file we already know we can't parse -
    # processing it should fail again cleanly, not raise.
    jd_id = _make_confirmed_jd()
    resume_id = _upload_one(jd_id, "bad.doc", b"legacy binary content", "application/msword")

    assert _process(resume_id) == ResumeStatus.FAILED.value
    with session_scope() as db:
        resume = resume_storage.get_resume(db, resume_id)
        assert "Unsupported file type" in resume.error_message


def test_rag_indexing_failure_fails_the_resume_even_if_extraction_succeeded(monkeypatch):
    """A resume without indexed chunks isn't actually ready to be scored -
    candidate extraction succeeding shouldn't be enough for SCORING.
    """
    _mock_extract(monkeypatch, CandidateExtractedFields(name="Ada Lovelace"))
    monkeypatch.setattr(
        "backend.services.resume.profile.vectorstore.index_resume",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("embeddings API unreachable")),
    )

    jd_id = _make_confirmed_jd()
    resume_id = _upload_one(jd_id, "r.docx", _docx_bytes(), "application/octet-stream")

    assert _process(resume_id) == ResumeStatus.FAILED.value
    with session_scope() as db:
        resume = resume_storage.get_resume(db, resume_id)
        assert "embeddings API unreachable" in resume.error_message
    # the candidate row still isn't considered final since the resume overall failed
    assert client.get(f"/api/v1/resumes/{resume_id}/candidate").status_code == 404


def test_reprocessing_after_reaching_scoring_leaves_status_unchanged(monkeypatch):
    """process_resume() itself has no notion of "already done" - that guard
    lives in the /process route (see tests/test_pipeline.py). Calling it
    again just re-extracts and stays at SCORING.
    """
    _mock_extract(monkeypatch, CandidateExtractedFields(name="Someone"))
    jd_id = _make_confirmed_jd()
    resume_id = _upload_one(jd_id, "r.docx", _docx_bytes(), "application/octet-stream")

    assert _process(resume_id) == ResumeStatus.SCORING.value
    assert _process(resume_id) == ResumeStatus.SCORING.value


def test_get_candidate_before_processing_404():
    jd_id = _make_confirmed_jd()
    resume_id = _upload_one(jd_id, "r.docx", _docx_bytes(), "application/octet-stream")
    assert client.get(f"/api/v1/resumes/{resume_id}/candidate").status_code == 404
