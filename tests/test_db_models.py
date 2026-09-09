"""Proves init_db() creates a working schema: every table, the FKs/relationships
between JD -> Resume -> Candidate -> ScreeningResult/Assessment, and that the
str-Enum columns round-trip correctly.
"""

import pytest

from backend.core.enums import Fit, JDStatus, ResumeStatus
from backend.db.models import Assessment, Candidate, JobDescription, Resume, ScreeningResult
from backend.db.session import session_scope


@pytest.fixture(autouse=True)
def _db(isolated_db):
    pass


def test_full_relationship_chain_persists_and_reads_back():
    with session_scope() as db:
        jd = JobDescription(
            filename="jd.pdf",
            storage_path="data/uploads/jds/jd.pdf",
            status=JDStatus.CONFIRMED,
            job_title="Backend Engineer",
            must_have_skills=["Python", "SQL"],
        )
        db.add(jd)
        db.flush()  # assigns jd.id without committing yet

        resume = Resume(
            jd_id=jd.id,
            filename="resume.pdf",
            storage_path="data/uploads/resumes/resume.pdf",
            file_size=1234,
            mime_type="application/pdf",
            status=ResumeStatus.DONE,
        )
        db.add(resume)
        db.flush()

        candidate = Candidate(resume_id=resume.id, name="Ada Lovelace", email="ada@example.com")
        db.add(candidate)
        db.flush()

        db.add(
            ScreeningResult(
                candidate_id=candidate.id,
                jd_id=jd.id,
                jd_version=jd.version,
                per_skill_scores={"Python": 9},
                overall_rating=88,
                fit=Fit.BEST,
                reason="Strong Python and SQL background.",
            )
        )
        db.add(
            Assessment(
                candidate_id=candidate.id,
                jd_id=jd.id,
                questions=[{"question": "Explain GIL", "skill_tag": "Python", "difficulty": "MEDIUM"}],
            )
        )

    with session_scope() as db:
        stored_jd = db.query(JobDescription).one()
        assert stored_jd.status == JDStatus.CONFIRMED  # enum round-trips, not raw string
        assert len(stored_jd.resumes) == 1

        stored_resume = stored_jd.resumes[0]
        assert stored_resume.candidate.name == "Ada Lovelace"
        assert stored_resume.candidate.screening_results[0].fit == Fit.BEST
        assert stored_resume.candidate.assessments[0].questions[0]["skill_tag"] == "Python"


def test_resume_requires_a_valid_jd_id():
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        with session_scope() as db:
            db.add(
                Resume(
                    jd_id=9999,  # no such JD
                    filename="orphan.pdf",
                    storage_path="x",
                    file_size=1,
                    status=ResumeStatus.PENDING,
                )
            )
