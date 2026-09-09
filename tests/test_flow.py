"""The whole recruiter journey, with the LLM stubbed out:
upload a JD -> bulk-upload resumes -> read the results table -> generate
interview questions.
"""

import pytest

from backend.schemas import LLMJobDescription, LLMQuestion, LLMQuestionSet, LLMScreening, SkillScore

JD_TEXT = """Senior Backend Engineer
We need 5+ years building Python APIs. Must have Python, FastAPI, PostgreSQL.
Nice to have Docker."""

STRONG_RESUME = "Priya Nair\npriya@example.com\n+91 98765 43210\n8 years Python and FastAPI."
WEAK_RESUME = "Sam Cole\nsam@example.com\nGraphic designer, 3 years Photoshop."


@pytest.fixture
def fake_llm(monkeypatch):
    """Return a canned answer per schema, so the flow is exercised without
    a network call or an API key."""

    def ask(prompt: str, schema):
        if schema is LLMJobDescription:
            return LLMJobDescription(
                title="Senior Backend Engineer",
                min_years=5,
                must_have_skills=["Python", "FastAPI", "PostgreSQL"],
                good_to_have_skills=["Docker"],
                responsibilities=["Build and maintain APIs"],
            )
        if schema is LLMScreening:
            strong = "Priya" in prompt
            return LLMScreening(
                name="Priya Nair" if strong else "Sam Cole",
                email="priya@example.com" if strong else "sam@example.com",
                phone="+919876543210" if strong else None,
                current_title="Backend Engineer" if strong else "Designer",
                total_experience_years=8.0 if strong else 3.0,
                relevant_experience_years=8.0 if strong else 0.0,
                skills=["Python", "FastAPI"] if strong else ["Photoshop"],
                skill_scores=[
                    SkillScore(skill="Python", score=9 if strong else 0),
                    SkillScore(skill="FastAPI", score=8 if strong else 0),
                    SkillScore(skill="PostgreSQL", score=7 if strong else 0),
                ],
                score=88 if strong else 12,
                reason="Strong match." if strong else "No backend experience.",
            )
        if schema is LLMQuestionSet:
            return LLMQuestionSet(
                questions=[
                    LLMQuestion(
                        question="Walk me through your FastAPI service design.",
                        skill="FastAPI",
                        difficulty="MEDIUM",
                        expected_answer="Routing, dependency injection, async handling.",
                    )
                ]
            )
        raise AssertionError(f"unexpected schema {schema}")

    monkeypatch.setattr("backend.services.ask", ask)


def test_full_journey(client, fake_llm, tmp_path):
    # --- 1. The TA team adds a JD -------------------------------------
    jd_file = tmp_path / "backend-role.txt"
    jd_file.write_text(JD_TEXT)

    response = client.post("/api/jds", files={"file": ("backend-role.txt", jd_file.read_bytes())})
    assert response.status_code == 201, response.text
    jd = response.json()
    assert jd["status"] == "DONE"
    assert jd["title"] == "Senior Backend Engineer"
    assert jd["must_have_skills"] == ["Python", "FastAPI", "PostgreSQL"]
    jd_id = jd["id"]

    # --- 2. Bulk-upload resumes of mixed quality ----------------------
    strong = tmp_path / "priya.txt"
    strong.write_text(STRONG_RESUME)
    weak = tmp_path / "sam.txt"
    weak.write_text(WEAK_RESUME)
    unsupported = tmp_path / "notes.pages"
    unsupported.write_bytes(b"junk")

    response = client.post(
        "/api/resumes",
        params={"jd_id": jd_id},
        files=[
            ("files", ("priya.txt", strong.read_bytes())),
            ("files", ("sam.txt", weak.read_bytes())),
            ("files", ("notes.pages", unsupported.read_bytes())),
        ],
    )
    assert response.status_code == 201, response.text
    summary = response.json()
    assert summary["uploaded"] == 2
    assert summary["rejected"] == 1  # the .pages file, without an LLM call

    # --- 3. Read the results table ------------------------------------
    rows = client.get("/api/resumes", params={"jd_id": jd_id}).json()
    assert len(rows) == 3

    best = rows[0]  # sorted best score first
    assert best["name"] == "Priya Nair"
    assert best["email"] == "priya@example.com"
    assert best["phone"] == "+919876543210"
    assert best["total_experience_years"] == 8.0
    assert best["relevant_experience_years"] == 8.0
    assert best["score"] == 88
    assert best["fit"] == "BEST"
    assert best["skill_scores"] == {"Python": 9, "FastAPI": 8, "PostgreSQL": 7}
    assert best["reason"]

    assert rows[1]["name"] == "Sam Cole"
    assert rows[1]["fit"] == "NO"

    # One bad file must not have disrupted the other two.
    rejected = rows[2]
    assert rejected["status"] == "FAILED"
    assert "Unsupported file type" in rejected["error"]

    # --- 4. Generate the tech-round questions -------------------------
    response = client.post(
        "/api/assessments", params={"resume_id": best["id"], "num_questions": 1}
    )
    assert response.status_code == 201, response.text
    questions = response.json()["questions"]
    assert len(questions) == 1
    assert questions[0]["skill"] == "FastAPI"
    assert questions[0]["difficulty"] == "MEDIUM"
    assert questions[0]["expected_answer"]


def test_one_bad_resume_does_not_stop_the_batch(client, fake_llm, tmp_path, monkeypatch):
    """The core resilience promise of a bulk upload."""
    jd_file = tmp_path / "jd.txt"
    jd_file.write_text(JD_TEXT)
    jd_id = client.post("/api/jds", files={"file": ("jd.txt", jd_file.read_bytes())}).json()["id"]

    calls = {"n": 0}
    real_ask = __import__("backend.services", fromlist=["ask"]).ask

    def flaky(prompt, schema):
        if schema is LLMScreening:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("provider exploded")
        return real_ask(prompt, schema)

    monkeypatch.setattr("backend.services.ask", flaky)

    good = tmp_path / "priya.txt"
    good.write_text(STRONG_RESUME)
    client.post(
        "/api/resumes",
        params={"jd_id": jd_id},
        files=[
            ("files", ("a.txt", good.read_bytes())),
            ("files", ("b.txt", good.read_bytes())),
        ],
    )

    rows = client.get("/api/resumes", params={"jd_id": jd_id}).json()
    statuses = sorted(r["status"] for r in rows)
    assert statuses == ["DONE", "FAILED"]
    failed = next(r for r in rows if r["status"] == "FAILED")
    assert "provider exploded" in failed["error"]


def test_resumes_rejected_until_the_jd_parses(client, tmp_path, monkeypatch):
    """A JD that failed to parse has no skills to score against."""

    def boom(prompt, schema):
        raise RuntimeError("no API key")

    monkeypatch.setattr("backend.services.ask", boom)

    jd_file = tmp_path / "jd.txt"
    jd_file.write_text(JD_TEXT)
    jd = client.post("/api/jds", files={"file": ("jd.txt", jd_file.read_bytes())}).json()
    assert jd["status"] == "FAILED"
    assert "no API key" in jd["error"]

    resume = tmp_path / "cv.txt"
    resume.write_text(STRONG_RESUME)
    response = client.post(
        "/api/resumes",
        params={"jd_id": jd["id"]},
        files=[("files", ("cv.txt", resume.read_bytes()))],
    )
    assert response.status_code == 400
    assert "job description" in response.json()["detail"].lower()
