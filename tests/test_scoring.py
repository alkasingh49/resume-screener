"""Tests for backend/services/scoring.py against a real temp DB - only the
LLM call itself is mocked (via _score_via_llm, same pattern as
extract_jd_fields/extract_candidate_fields). RAG retrieval runs for real
against a real local Chroma collection with the keyword-based fake
embedding from tests/test_vectorstore.py.
"""

import pytest

from backend.core.enums import ExperienceSource, Fit, JDStatus, ResumeStatus, ScreeningResultStatus
from backend.db.models.candidate import Candidate
from backend.db.models.job_description import JobDescription
from backend.db.models.resume import Resume
from backend.db.models.screening_result import ScreeningResult
from backend.db.session import session_scope
from backend.schemas.screening import ScoringExtractedFields
from backend.services import scoring, vectorstore
from tests.test_vectorstore import KeywordEmbeddings


@pytest.fixture(autouse=True)
def _db_and_fake_embeddings(isolated_db, monkeypatch):
    monkeypatch.setattr(vectorstore, "get_embeddings", lambda: KeywordEmbeddings())


def _mock_llm(monkeypatch, fields: ScoringExtractedFields):
    monkeypatch.setattr("backend.services.scoring._score_via_llm", lambda *a, **k: fields)


def _make_jd_resume_candidate(*, must_have=None, jd_version=1, jd_status=JDStatus.CONFIRMED):
    with session_scope() as db:
        jd = JobDescription(
            filename="jd.pdf",
            storage_path="x",
            status=jd_status,
            job_title="Backend Engineer",
            must_have_skills=must_have if must_have is not None else ["Python"],
            good_to_have_skills=["Docker"],
            version=jd_version,
        )
        db.add(jd)
        db.flush()

        resume = Resume(
            jd_id=jd.id,
            filename="r.docx",
            storage_path="x",
            file_size=1,
            file_hash="abc123",
            status=ResumeStatus.SCORING,
        )
        db.add(resume)
        db.flush()

        candidate = Candidate(
            resume_id=resume.id,
            name="Ada Lovelace",
            current_title="Backend Engineer",
            total_experience_years=5,
            total_experience_source=ExperienceSource.COMPUTED,
            skills=["Python", "Docker"],
        )
        db.add(candidate)
        db.flush()

        return jd.id, resume.id


def _default_fields(**overrides) -> ScoringExtractedFields:
    base = dict(
        per_skill_scores={"Python": 9, "Docker": 6},
        overall_rating=80,
        relevant_experience_years=4.0,
        reason="Strong Python background evidenced across multiple roles.",
    )
    base.update(overrides)
    return ScoringExtractedFields(**base)


def test_score_candidate_creates_a_current_result(monkeypatch):
    _mock_llm(monkeypatch, _default_fields())
    jd_id, resume_id = _make_jd_resume_candidate()

    vectorstore.index_resume(jd_id, resume_id, "Backend engineer skilled in Python and Docker.")

    with session_scope() as db:
        jd = db.get(JobDescription, jd_id)
        resume = db.get(Resume, resume_id)
        result = scoring.score_candidate(db, jd=jd, resume=resume)
        result_id = result.id

    with session_scope() as db:
        stored = db.get(ScreeningResult, result_id)
        assert stored.overall_rating == 80
        assert stored.per_skill_scores == {"Python": 9, "Docker": 6}
        assert stored.relevant_experience_years == 4.0
        assert stored.result_status == ScreeningResultStatus.CURRENT
        assert stored.jd_version == 1
        assert stored.reason


@pytest.mark.parametrize(
    "overall_rating,expected_fit",
    [(90, Fit.BEST), (75, Fit.BEST), (60, Fit.MEDIUM), (45, Fit.MEDIUM), (30, Fit.NO)],
)
def test_fit_is_computed_from_config_thresholds_not_asked_of_llm(monkeypatch, overall_rating, expected_fit):
    # defaults: FIT_THRESHOLD_BEST=75, FIT_THRESHOLD_MEDIUM=45
    _mock_llm(monkeypatch, _default_fields(overall_rating=overall_rating))
    jd_id, resume_id = _make_jd_resume_candidate()
    vectorstore.index_resume(jd_id, resume_id, "Python developer.")

    with session_scope() as db:
        jd = db.get(JobDescription, jd_id)
        resume = db.get(Resume, resume_id)
        result = scoring.score_candidate(db, jd=jd, resume=resume)
        assert result.fit == expected_fit


def test_scoring_fails_without_a_candidate_profile():
    jd_id, resume_id = _make_jd_resume_candidate()
    with session_scope() as db:
        resume = db.get(Resume, resume_id)
        db.delete(resume.candidate)
        db.flush()

    with session_scope() as db:
        jd = db.get(JobDescription, jd_id)
        resume = db.get(Resume, resume_id)
        with pytest.raises(ValueError, match="no extracted candidate profile"):
            scoring.score_candidate(db, jd=jd, resume=resume)


def test_rescoring_marks_prior_current_result_stale_and_keeps_history(monkeypatch):
    jd_id, resume_id = _make_jd_resume_candidate()
    vectorstore.index_resume(jd_id, resume_id, "Python developer.")

    _mock_llm(monkeypatch, _default_fields(overall_rating=50))
    with session_scope() as db:
        jd = db.get(JobDescription, jd_id)
        resume = db.get(Resume, resume_id)
        first = scoring.score_candidate(db, jd=jd, resume=resume)
        first_id = first.id

    _mock_llm(monkeypatch, _default_fields(overall_rating=90))
    with session_scope() as db:
        jd = db.get(JobDescription, jd_id)
        resume = db.get(Resume, resume_id)
        second = scoring.score_candidate(db, jd=jd, resume=resume)
        second_id = second.id

    with session_scope() as db:
        old = db.get(ScreeningResult, first_id)
        new = db.get(ScreeningResult, second_id)
        assert old.result_status == ScreeningResultStatus.STALE
        assert new.result_status == ScreeningResultStatus.CURRENT
        assert old.overall_rating == 50  # history preserved, not overwritten
        assert new.overall_rating == 90


def test_cache_key_includes_jd_version_so_an_edited_jd_does_not_reuse_a_stale_cached_score(monkeypatch):
    """Not a full cache round-trip (that's covered in test_llm_wrapper.py) -
    just proves the cache key actually changes when jd.version changes, so a
    JD edit can't silently serve a score computed against the old JD text.
    """
    seen_keys = []
    monkeypatch.setattr(
        "backend.services.scoring._score_via_llm",
        lambda prompt, *, operation, cache_key: (seen_keys.append(cache_key), _default_fields())[1],
    )

    jd_id, resume_id = _make_jd_resume_candidate(jd_version=1)
    vectorstore.index_resume(jd_id, resume_id, "Python developer.")
    with session_scope() as db:
        jd = db.get(JobDescription, jd_id)
        resume = db.get(Resume, resume_id)
        scoring.score_candidate(db, jd=jd, resume=resume)
        jd.version = 2

    with session_scope() as db:
        jd = db.get(JobDescription, jd_id)
        resume = db.get(Resume, resume_id)
        scoring.score_candidate(db, jd=jd, resume=resume)

    assert len(seen_keys) == 2
    assert seen_keys[0] != seen_keys[1]
    assert "jd_version=1" in seen_keys[0]
    assert "jd_version=2" in seen_keys[1]
