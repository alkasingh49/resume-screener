"""Tests for the pure export-formatting logic behind the Assessments page's
download buttons - no Streamlit/network needed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "frontend"))

from components.assessment_export import candidate_markdown, interviewer_csv, interviewer_markdown  # noqa: E402

QUESTIONS = [
    {
        "question": "Explain the GIL.",
        "skill_tag": "Python",
        "difficulty": "MEDIUM",
        "expected_answer_points": ["Mentions single-threaded bytecode execution", "Mentions its effect on CPU-bound threading"],
    },
    {
        "question": "What is a covering index?",
        "skill_tag": "SQL",
        "difficulty": "HARD",
        "expected_answer_points": ["Index contains all queried columns"],
    },
]


def test_interviewer_markdown_includes_answer_points():
    md = interviewer_markdown(QUESTIONS)
    assert "Explain the GIL." in md
    assert "Mentions single-threaded bytecode execution" in md
    assert "[MEDIUM] Python" in md
    assert "[HARD] SQL" in md


def test_candidate_markdown_strips_answer_points_and_skill_tag():
    md = candidate_markdown(QUESTIONS)
    assert "Explain the GIL." in md
    assert "What is a covering index?" in md
    assert "Mentions single-threaded bytecode execution" not in md  # answer points gone
    assert "Python" not in md  # skill tag gone too (would hint at the answer)
    assert "SQL" not in md


def test_interviewer_csv_has_header_and_one_row_per_question():
    csv_bytes = interviewer_csv(QUESTIONS)
    text = csv_bytes.decode("utf-8")
    lines = text.strip().splitlines()
    assert lines[0] == "#,Difficulty,Skill,Question,Expected Answer Points"
    assert len(lines) == 1 + len(QUESTIONS)
    assert "Explain the GIL." in lines[1]
    assert "Mentions single-threaded bytecode execution; Mentions its effect on CPU-bound threading" in lines[1]


def test_empty_questions_produce_valid_but_empty_exports():
    assert interviewer_markdown([]) == "# Technical Assessment (Interviewer Copy)\n"
    assert candidate_markdown([]) == "# Technical Assessment\n"
    csv_text = interviewer_csv([]).decode("utf-8").strip()
    assert csv_text == "#,Difficulty,Skill,Question,Expected Answer Points"


def test_missing_expected_answer_points_does_not_crash():
    question = {"question": "Q", "skill_tag": "Python", "difficulty": "EASY"}  # no expected_answer_points key
    assert "Q" in interviewer_markdown([question])
    assert "Q" in interviewer_csv([question]).decode("utf-8")
