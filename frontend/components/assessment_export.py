"""Build export strings for a generated assessment - interviewer versions
(with expected answer points) and the candidate-facing version (answer
points stripped). Pure functions, no Streamlit/network calls - easy to
test directly and reuse from frontend/pages/4_Assessments.py.
"""

import csv
import io


def interviewer_markdown(questions: list[dict]) -> str:
    lines = ["# Technical Assessment (Interviewer Copy)", ""]
    for i, q in enumerate(questions, start=1):
        lines.append(f"## Q{i}. [{q['difficulty']}] {q['skill_tag']}")
        lines.append(q["question"])
        lines.append("")
        lines.append("**Expected answer points:**")
        for point in q.get("expected_answer_points") or []:
            lines.append(f"- {point}")
        lines.append("")
    return "\n".join(lines)


def candidate_markdown(questions: list[dict]) -> str:
    """Same structure, minus expected_answer_points and the skill tag (which
    would hint at what's being tested)."""
    lines = ["# Technical Assessment", ""]
    for i, q in enumerate(questions, start=1):
        lines.append(f"## Question {i} ({q['difficulty']})")
        lines.append(q["question"])
        lines.append("")
    return "\n".join(lines)


def interviewer_csv(questions: list[dict]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["#", "Difficulty", "Skill", "Question", "Expected Answer Points"])
    for i, q in enumerate(questions, start=1):
        writer.writerow(
            [
                i,
                q["difficulty"],
                q["skill_tag"],
                q["question"],
                "; ".join(q.get("expected_answer_points") or []),
            ]
        )
    return buffer.getvalue().encode("utf-8")
