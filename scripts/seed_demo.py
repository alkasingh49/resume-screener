"""Seed the DB with a complete demo scenario - one confirmed JD, four scored
candidates spanning Best/Medium/No fit, and one sample assessment for the
top candidate - entirely via direct DB writes (no LLM calls, no API key
needed), so a fresh clone shows a fully populated app immediately.

Usage:
    python scripts/seed_demo.py            # add demo data
    python scripts/seed_demo.py --reset    # wipe existing JD/resume/
                                            # candidate/screening/assessment
                                            # data first, then seed fresh
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core.config import get_settings  # noqa: E402
from backend.core.enums import ExperienceSource, Fit, JDStatus, ResumeStatus, ScreeningResultStatus  # noqa: E402
from backend.core.logging import setup_logging  # noqa: E402
from backend.db.models.assessment import Assessment  # noqa: E402
from backend.db.models.candidate import Candidate  # noqa: E402
from backend.db.models.job_description import JobDescription  # noqa: E402
from backend.db.models.resume import Resume  # noqa: E402
from backend.db.models.screening_result import ScreeningResult  # noqa: E402
from backend.db.session import init_db, session_scope  # noqa: E402

CANDIDATES = [
    dict(
        name="Ada Lovelace",
        email="ada.lovelace@example.com",
        phone="+1-555-0101",
        location="Remote",
        current_title="Senior Backend Engineer",
        current_company="Analytical Engines Inc",
        total_experience_years=6.5,
        skills=["Python", "FastAPI", "SQL", "Docker", "Kubernetes", "AWS"],
        education=[{"degree": "BS Computer Science", "institution": "MIT", "year": "2017"}],
        work_history=[
            {
                "title": "Senior Backend Engineer",
                "company": "Analytical Engines Inc",
                "start_date": "Mar 2021",
                "end_date": "Present",
                "description": "Leads the backend platform team; builds FastAPI microservices deployed on Kubernetes.",
            },
            {
                "title": "Backend Engineer",
                "company": "Difference Systems",
                "start_date": "Jun 2017",
                "end_date": "Feb 2021",
                "description": "Built Python/SQL data pipelines and internal APIs.",
            },
        ],
        certifications=["AWS Certified Solutions Architect"],
        scores={"Python": 9, "SQL": 8, "Docker": 9, "Kubernetes": 8, "AWS": 7},
        overall_rating=91,
        fit=Fit.BEST,
        relevant_experience_years=6.5,
        reason=(
            "Extensive, directly relevant backend experience with Python, Docker, and Kubernetes "
            "across two roles; strong match on every must-have skill."
        ),
    ),
    dict(
        name="Grace Hopper",
        email="grace.hopper@example.com",
        phone="+1-555-0102",
        location="New York, NY",
        current_title="Backend Developer",
        current_company="Compiler Corp",
        total_experience_years=8.0,
        skills=["Python", "SQL", "Java"],
        education=[{"degree": "MS Computer Science", "institution": "Yale", "year": "1934"}],
        work_history=[
            {
                "title": "Backend Developer",
                "company": "Compiler Corp",
                "start_date": "Jan 2016",
                "end_date": "Present",
                "description": "Maintains Java and Python services; some SQL reporting work.",
            },
        ],
        certifications=[],
        scores={"Python": 6, "SQL": 6, "Docker": 3, "Kubernetes": 1, "AWS": 2},
        overall_rating=58,
        fit=Fit.MEDIUM,
        relevant_experience_years=2.5,
        reason=(
            "Solid Python and SQL background but limited hands-on containerization experience; "
            "most of her tenure has been in Java-heavy systems."
        ),
    ),
    dict(
        name="Alan Turing",
        email="alan.turing@example.com",
        phone="+1-555-0103",
        location="London, UK",
        current_title="Research Assistant",
        current_company="Bletchley Labs",
        total_experience_years=1.5,
        skills=["Python", "Mathematics"],
        education=[{"degree": "PhD Mathematics", "institution": "Princeton", "year": "1938"}],
        work_history=[
            {
                "title": "Research Assistant",
                "company": "Bletchley Labs",
                "start_date": "Sep 2024",
                "end_date": "Present",
                "description": "Academic research, with some Python scripting for data analysis.",
            },
        ],
        certifications=[],
        scores={"Python": 4, "SQL": 1, "Docker": 0, "Kubernetes": 0, "AWS": 0},
        overall_rating=28,
        fit=Fit.NO,
        relevant_experience_years=0.3,
        reason=(
            "Primarily academic/research background with minimal production engineering experience "
            "and no evidence of the required infrastructure skills."
        ),
    ),
    dict(
        name="Katherine Johnson",
        email="katherine.johnson@example.com",
        phone="+1-555-0104",
        location="Hampton, VA",
        current_title="Backend Engineer",
        current_company="Orbital Systems",
        total_experience_years=4.0,
        skills=["Python", "SQL", "Docker", "AWS"],
        education=[{"degree": "BS Mathematics", "institution": "West Virginia State", "year": "2019"}],
        work_history=[
            {
                "title": "Backend Engineer",
                "company": "Orbital Systems",
                "start_date": "Jul 2020",
                "end_date": "Present",
                "description": "Builds and deploys Dockerized Python services on AWS.",
            },
        ],
        certifications=["AWS Certified Developer Associate"],
        scores={"Python": 8, "SQL": 7, "Docker": 7, "Kubernetes": 3, "AWS": 8},
        overall_rating=76,
        fit=Fit.BEST,
        relevant_experience_years=4.0,
        reason=(
            "Strong, directly relevant Python/Docker/AWS experience; Kubernetes exposure is limited "
            "but the rest of the must-have skill set is well covered."
        ),
    ),
]

SAMPLE_ASSESSMENT_QUESTIONS = [
    {
        "question": (
            "Explain the difference between multiprocessing and multithreading in Python, "
            "and when you'd choose each."
        ),
        "skill_tag": "Python",
        "difficulty": "MEDIUM",
        "expected_answer_points": [
            "Mentions the GIL and its effect on CPU-bound threads",
            "Multiprocessing for CPU-bound work, threading/asyncio for I/O-bound work",
        ],
    },
    {
        "question": "How would you design a multi-stage Dockerfile to keep a Python service's image small?",
        "skill_tag": "Docker",
        "difficulty": "HARD",
        "expected_answer_points": [
            "Separate build and runtime stages",
            "Only copy built artifacts/dependencies into the final stage",
            "Use a slim base image",
        ],
    },
    {
        "question": "What's the difference between a Kubernetes Deployment and a StatefulSet?",
        "skill_tag": "Kubernetes",
        "difficulty": "MEDIUM",
        "expected_answer_points": [
            "StatefulSet gives stable network identity and storage per pod",
            "Used for stateful workloads like databases; Deployment is for stateless replicas",
        ],
    },
]


def _wipe_existing(db) -> None:
    """Delete in FK-safe order (children before parents)."""
    for model in (Assessment, ScreeningResult, Candidate, Resume, JobDescription):
        db.query(model).delete()


def seed(reset: bool) -> None:
    setup_logging()
    settings = get_settings()
    settings.ensure_data_dirs()
    init_db()

    with session_scope() as db:
        if reset:
            _wipe_existing(db)

        jd = JobDescription(
            filename="backend_engineer_jd.pdf",
            storage_path="seed:no-file",
            raw_text=(
                "Job Title: Backend Engineer\n"
                "Department: Engineering\nLocation: Remote\nEmployment Type: Full-time\n"
                "Experience: 3 to 7 years\n"
                "Must-have skills: Python, SQL, Docker, Kubernetes\n"
                "Good-to-have skills: AWS\n"
                "Responsibilities:\n- Design and build backend services\n"
                "- Own API contracts and data models\n- Deploy and operate services on Kubernetes\n"
                "Qualifications: Bachelor's degree in Computer Science or equivalent experience."
            ),
            status=JDStatus.CONFIRMED,
            job_title="Backend Engineer",
            department="Engineering",
            location="Remote",
            employment_type="Full-time",
            min_years=3,
            max_years=7,
            must_have_skills=["Python", "SQL", "Docker", "Kubernetes"],
            good_to_have_skills=["AWS"],
            key_responsibilities=[
                "Design and build backend services",
                "Own API contracts and data models",
                "Deploy and operate services on Kubernetes",
            ],
            qualifications="Bachelor's degree in Computer Science or equivalent experience.",
            version=1,
        )
        db.add(jd)
        db.flush()

        top_candidate_id = None
        top_resume_id = None
        top_rating = -1

        for c in CANDIDATES:
            resume = Resume(
                jd_id=jd.id,
                filename=f"{c['name'].replace(' ', '_').lower()}_resume.pdf",
                storage_path="seed:no-file",
                file_size=12345,
                mime_type="application/pdf",
                status=ResumeStatus.DONE,
                raw_text=f"Resume for {c['name']}. {c['current_title']} at {c['current_company']}.",
            )
            db.add(resume)
            db.flush()

            candidate = Candidate(resume_id=resume.id)
            resume.candidate = candidate  # sets resume_id + keeps the relationship in sync (see profile.py)
            candidate.name = c["name"]
            candidate.email = c["email"]
            candidate.phone = c["phone"]
            candidate.location = c["location"]
            candidate.current_title = c["current_title"]
            candidate.current_company = c["current_company"]
            candidate.total_experience_years = c["total_experience_years"]
            candidate.total_experience_source = ExperienceSource.COMPUTED
            candidate.skills = c["skills"]
            candidate.education = c["education"]
            candidate.work_history = c["work_history"]
            candidate.certifications = c["certifications"]
            db.flush()

            db.add(
                ScreeningResult(
                    candidate_id=candidate.id,
                    jd_id=jd.id,
                    jd_version=jd.version,
                    per_skill_scores=c["scores"],
                    overall_rating=c["overall_rating"],
                    relevant_experience_years=c["relevant_experience_years"],
                    fit=c["fit"],
                    reason=c["reason"],
                    result_status=ScreeningResultStatus.CURRENT,
                    model_name="seed-demo-data",
                )
            )

            if c["overall_rating"] > top_rating:
                top_rating = c["overall_rating"]
                top_candidate_id = candidate.id
                top_resume_id = resume.id

        db.add(
            Assessment(
                candidate_id=top_candidate_id,
                jd_id=jd.id,
                questions=SAMPLE_ASSESSMENT_QUESTIONS,
            )
        )

        print(f"Seeded JD id={jd.id} ('{jd.job_title}', CONFIRMED)")
        print(f"Seeded {len(CANDIDATES)} candidates with screening results")
        print(f"Seeded 1 assessment for the top candidate (resume_id={top_resume_id})")

    print(
        "\nDone. Run `make run-backend` and `make run-frontend`, then open "
        "Screening Results and Assessments to see the seeded data."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--reset", action="store_true", help="Delete existing JD/resume/candidate/screening/assessment data first"
    )
    args = parser.parse_args()
    seed(reset=args.reset)
