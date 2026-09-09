"""One test that walks the entire product flow end to end through the real
HTTP routes - JD upload/review/confirm, resume upload (auto-triggering the
background parse+score pipeline), screening results, and assessment
generation - proving the pieces actually click together as a system, not
just individually per-phase. Every other test file covers its own phase in
much more depth (edge cases, failure modes, bug regressions); this one is
deliberately narrow and only walks the happy path.

Only the LLM/embedding calls are mocked - everything else (DB, real text
extraction from a real fixture file, real RAG chunking against a local
Chroma collection) is exercised for real, same policy as every other test
file in this project (see docs/BUILD_LOG.md's closing note).
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.core.enums import ResumeStatus
from backend.main import app
from backend.schemas.assessment import AssessmentGeneratedFields, AssessmentQuestion
from backend.schemas.candidate import CandidateExtractedFields, WorkHistoryEntry
from backend.schemas.jd import JDExtractedFields
from backend.schemas.screening import ScoringExtractedFields
from backend.services import vectorstore
from tests.test_vectorstore import KeywordEmbeddings

FIXTURES = Path(__file__).parent / "fixtures"
client = TestClient(app)


@pytest.fixture(autouse=True)
def _db_and_fakes(isolated_db, monkeypatch):
    monkeypatch.setattr(vectorstore, "get_embeddings", lambda: KeywordEmbeddings())


def test_full_journey_from_jd_upload_to_assessment_export_data(monkeypatch):
    # ---- 1. JD: upload, review/edit, confirm ----
    monkeypatch.setattr(
        "backend.api.v1.routes.jd.extract_jd_fields",
        lambda jd: JDExtractedFields(
            job_title="Backend Engineer",
            must_have_skills=["Python", "SQL"],
            good_to_have_skills=["Docker"],
            min_years=3,
            max_years=7,
            key_responsibilities=["Build backend services"],
            qualifications="BS in CS or equivalent.",
        ),
    )
    upload = client.post(
        "/api/v1/jds/upload", files={"file": ("jd.pdf", (FIXTURES / "sample_jd.pdf").read_bytes(), "application/pdf")}
    )
    assert upload.status_code == 200
    jd = upload.json()
    assert jd["status"] == "PARSED"  # complete on first pass, no manual review needed
    jd_id = jd["id"]

    confirm = client.post(f"/api/v1/jds/{jd_id}/confirm")
    assert confirm.status_code == 200
    assert confirm.json()["status"] == "CONFIRMED"

    # ---- 2. Resume: bulk upload, auto-triggered pipeline (parse + score) ----
    monkeypatch.setattr(
        "backend.services.resume.profile.extract_candidate_fields",
        lambda resume: CandidateExtractedFields(
            name="Ada Lovelace",
            email="ada@example.com",
            phone="+1-555-0100",
            current_title="Backend Engineer",
            skills=["Python", "SQL", "Docker"],
            work_history=[
                WorkHistoryEntry(title="Backend Engineer", company="Acme", start_date="Jan 2020", end_date="Present")
            ],
        ),
    )
    monkeypatch.setattr(
        "backend.services.scoring._score_via_llm",
        lambda *a, **k: ScoringExtractedFields(
            per_skill_scores={"Python": 9, "SQL": 8, "Docker": 7},
            overall_rating=88,
            relevant_experience_years=5.5,
            reason="Strong, directly relevant backend experience across all must-have skills.",
        ),
    )

    resume_upload = client.post(
        f"/api/v1/resumes/upload?jd_id={jd_id}",
        files=[("files", ("ada.docx", (FIXTURES / "sample_resume.docx").read_bytes(), "application/octet-stream"))],
    )
    assert resume_upload.status_code == 200
    resume_id = resume_upload.json()["resumes"][0]["id"]

    # TestClient runs BackgroundTasks synchronously, so the pipeline has
    # already run by the time the upload response comes back.
    resume = client.get(f"/api/v1/resumes/{resume_id}").json()
    assert resume["status"] == ResumeStatus.DONE.value

    # ---- 3. Screening results: candidate shows up correctly scored ----
    table = client.get(f"/api/v1/screening/results/table?jd_id={jd_id}").json()
    assert len(table) == 1
    row = table[0]
    assert row["resume_id"] == resume_id
    assert row["name"] == "Ada Lovelace"
    assert row["fit"] == "BEST"  # overall_rating=88 >= default FIT_THRESHOLD_BEST=75
    assert row["overall_rating"] == 88
    assert row["per_skill_scores"] == {"Python": 9, "SQL": 8, "Docker": 7}

    result_by_resume = client.get(f"/api/v1/screening/results/by-resume/{resume_id}").json()
    assert result_by_resume["jd_version"] == 1

    # ---- 4. Assessment: generate, list, fetch ----
    monkeypatch.setattr(
        "backend.services.assessment._generate_via_llm",
        lambda *a, **k: AssessmentGeneratedFields(
            questions=[
                AssessmentQuestion(
                    question="Explain the GIL's effect on Python multithreading.",
                    skill_tag="Python",
                    difficulty="MEDIUM",
                    expected_answer_points=["Mentions single bytecode execution at a time"],
                ),
                AssessmentQuestion(
                    question="What is a covering index?",
                    skill_tag="SQL",
                    difficulty="EASY",
                    expected_answer_points=["Index contains all queried columns"],
                ),
            ]
        ),
    )
    generate = client.post(
        "/api/v1/assessments/generate",
        json={"resume_id": resume_id, "num_easy": 1, "num_medium": 1, "num_hard": 0},
    )
    assert generate.status_code == 200
    assessment = generate.json()
    assert len(assessment["questions"]) == 2
    assert {q["difficulty"] for q in assessment["questions"]} == {"EASY", "MEDIUM"}

    listed = client.get(f"/api/v1/assessments?resume_id={resume_id}").json()
    assert len(listed) == 1
    assert listed[0]["id"] == assessment["id"]

    fetched = client.get(f"/api/v1/assessments/{assessment['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["candidate_id"] == assessment["candidate_id"]
