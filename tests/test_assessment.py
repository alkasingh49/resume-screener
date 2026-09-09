"""Tests for assessment generation - service logic (overlap-skill selection)
and the API routes, against a real temp DB with the LLM call mocked (same
pattern as extract_jd_fields/extract_candidate_fields/_score_via_llm).
"""

import pytest
from fastapi.testclient import TestClient

from backend.core.enums import Difficulty, ExperienceSource, JDStatus, ResumeStatus
from backend.db.models.candidate import Candidate
from backend.db.models.job_description import JobDescription
from backend.db.models.resume import Resume
from backend.db.session import session_scope
from backend.main import app
from backend.schemas.assessment import AssessmentGeneratedFields, AssessmentQuestion
from backend.services import assessment as assessment_service

client = TestClient(app)


@pytest.fixture(autouse=True)
def _db(isolated_db):
    pass


def _mock_llm(monkeypatch, fields: AssessmentGeneratedFields):
    monkeypatch.setattr("backend.services.assessment._generate_via_llm", lambda *a, **k: fields)


def _default_fields(n_easy=1, n_medium=1, n_hard=1) -> AssessmentGeneratedFields:
    questions = []
    for i in range(n_easy):
        questions.append(
            AssessmentQuestion(question=f"Easy Q{i}", skill_tag="Python", difficulty=Difficulty.EASY,
                                expected_answer_points=["point a"])
        )
    for i in range(n_medium):
        questions.append(
            AssessmentQuestion(question=f"Medium Q{i}", skill_tag="SQL", difficulty=Difficulty.MEDIUM,
                                expected_answer_points=["point b"])
        )
    for i in range(n_hard):
        questions.append(
            AssessmentQuestion(question=f"Hard Q{i}", skill_tag="Docker", difficulty=Difficulty.HARD,
                                expected_answer_points=["point c"])
        )
    return AssessmentGeneratedFields(questions=questions)


def _make_jd_and_resume(*, must_have=None, good_to_have=None, candidate_skills=None) -> tuple[int, int]:
    with session_scope() as db:
        jd = JobDescription(
            filename="jd.pdf",
            storage_path="x",
            status=JDStatus.CONFIRMED,
            job_title="Backend Engineer",
            must_have_skills=must_have if must_have is not None else ["Python", "SQL"],
            good_to_have_skills=good_to_have if good_to_have is not None else ["Docker"],
        )
        db.add(jd)
        db.flush()

        resume = Resume(
            jd_id=jd.id, filename="r.pdf", storage_path="x", file_size=1, status=ResumeStatus.DONE
        )
        db.add(resume)
        db.flush()

        candidate = Candidate(
            resume_id=resume.id,
            name="Ada Lovelace",
            skills=candidate_skills if candidate_skills is not None else ["Python", "SQL", "Docker"],
            total_experience_years=5,
            total_experience_source=ExperienceSource.COMPUTED,
        )
        db.add(candidate)
        db.flush()
        return jd.id, resume.id


def test_overlap_skills_intersects_jd_and_candidate_case_insensitively():
    jd_id, resume_id = _make_jd_and_resume(
        must_have=["python", "Go"], good_to_have=["AWS"], candidate_skills=["Python", "Rust"]
    )
    with session_scope() as db:
        jd = db.get(JobDescription, jd_id)
        resume = db.get(Resume, resume_id)
        overlap = assessment_service._overlap_skills(jd, resume.candidate)
        assert overlap == ["python"]  # only the case-insensitive match, original casing preserved


def test_overlap_falls_back_to_must_have_skills_when_no_overlap():
    jd_id, resume_id = _make_jd_and_resume(
        must_have=["Rust", "Go"], good_to_have=[], candidate_skills=["Python"]
    )
    with session_scope() as db:
        jd = db.get(JobDescription, jd_id)
        resume = db.get(Resume, resume_id)
        overlap = assessment_service._overlap_skills(jd, resume.candidate)
        assert overlap == ["Rust", "Go"]


def test_generate_endpoint_requires_at_least_one_question():
    jd_id, resume_id = _make_jd_and_resume()
    response = client.post(
        "/api/v1/assessments/generate",
        json={"resume_id": resume_id, "num_easy": 0, "num_medium": 0, "num_hard": 0},
    )
    assert response.status_code == 400


def test_generate_endpoint_requires_existing_resume():
    response = client.post(
        "/api/v1/assessments/generate", json={"resume_id": 9999, "num_easy": 1, "num_medium": 0, "num_hard": 0}
    )
    assert response.status_code == 404


def test_generate_requires_a_candidate_profile():
    with session_scope() as db:
        jd = JobDescription(filename="jd.pdf", storage_path="x", status=JDStatus.CONFIRMED, job_title="Eng")
        db.add(jd)
        db.flush()
        resume = Resume(jd_id=jd.id, filename="r.pdf", storage_path="x", file_size=1, status=ResumeStatus.PENDING)
        db.add(resume)
        db.flush()
        resume_id = resume.id

    response = client.post(
        "/api/v1/assessments/generate", json={"resume_id": resume_id, "num_easy": 1, "num_medium": 0, "num_hard": 0}
    )
    assert response.status_code == 404


def test_generate_creates_and_returns_the_assessment(monkeypatch):
    _mock_llm(monkeypatch, _default_fields(n_easy=2, n_medium=1, n_hard=1))
    jd_id, resume_id = _make_jd_and_resume()

    response = client.post(
        "/api/v1/assessments/generate",
        json={"resume_id": resume_id, "num_easy": 2, "num_medium": 1, "num_hard": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["questions"]) == 4
    difficulties = [q["difficulty"] for q in body["questions"]]
    assert difficulties.count("EASY") == 2
    assert difficulties.count("MEDIUM") == 1
    assert difficulties.count("HARD") == 1
    assert body["questions"][0]["expected_answer_points"] == ["point a"]


def test_generation_failure_is_a_clean_error_not_500(monkeypatch):
    def _raise(*a, **k):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr("backend.services.assessment._generate_via_llm", _raise)
    jd_id, resume_id = _make_jd_and_resume()

    response = client.post(
        "/api/v1/assessments/generate", json={"resume_id": resume_id, "num_easy": 1, "num_medium": 0, "num_hard": 0}
    )
    assert response.status_code == 502
    assert "LLM unavailable" in response.json()["detail"]


def test_list_assessments_returns_newest_first(monkeypatch):
    jd_id, resume_id = _make_jd_and_resume()

    _mock_llm(monkeypatch, _default_fields(n_easy=1, n_medium=0, n_hard=0))
    first = client.post(
        "/api/v1/assessments/generate", json={"resume_id": resume_id, "num_easy": 1, "num_medium": 0, "num_hard": 0}
    ).json()

    _mock_llm(monkeypatch, _default_fields(n_easy=0, n_medium=2, n_hard=0))
    second = client.post(
        "/api/v1/assessments/generate", json={"resume_id": resume_id, "num_easy": 0, "num_medium": 2, "num_hard": 0}
    ).json()

    listed = client.get(f"/api/v1/assessments?resume_id={resume_id}").json()
    assert [a["id"] for a in listed] == [second["id"], first["id"]]


def test_list_assessments_requires_candidate_profile():
    assert client.get("/api/v1/assessments?resume_id=9999").status_code == 404


def test_get_assessment_by_id(monkeypatch):
    _mock_llm(monkeypatch, _default_fields(n_easy=1, n_medium=0, n_hard=0))
    jd_id, resume_id = _make_jd_and_resume()
    created = client.post(
        "/api/v1/assessments/generate", json={"resume_id": resume_id, "num_easy": 1, "num_medium": 0, "num_hard": 0}
    ).json()

    fetched = client.get(f"/api/v1/assessments/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["questions"][0]["question"] == "Easy Q0"


def test_get_missing_assessment_404():
    assert client.get("/api/v1/assessments/9999").status_code == 404


def test_cache_key_includes_difficulty_mix_and_jd_version(monkeypatch):
    """Two different difficulty mixes (or a JD version bump) must not
    silently share a cached generation result.
    """
    seen_keys = []
    monkeypatch.setattr(
        "backend.services.assessment._generate_via_llm",
        lambda prompt, *, operation, cache_key: (seen_keys.append(cache_key), _default_fields())[1],
    )
    jd_id, resume_id = _make_jd_and_resume()

    with session_scope() as db:
        jd = db.get(JobDescription, jd_id)
        resume = db.get(Resume, resume_id)
        assessment_service.generate_assessment(db, jd=jd, resume=resume, num_easy=1, num_medium=1, num_hard=1)
        assessment_service.generate_assessment(db, jd=jd, resume=resume, num_easy=3, num_medium=0, num_hard=0)

    assert len(seen_keys) == 2
    assert seen_keys[0] != seen_keys[1]
