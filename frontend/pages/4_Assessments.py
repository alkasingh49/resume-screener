"""Generate a targeted technical assessment for a scored candidate, and
export it - interviewer version (with expected answer points) as Markdown
or CSV, candidate-facing version (answer points stripped) as Markdown.
"""

import requests
import streamlit as st

from components.assessment_export import candidate_markdown, interviewer_csv, interviewer_markdown
from components.flash import flash, render_pending_flash
from services import api_client

st.set_page_config(page_title="Assessments", page_icon="📝", layout="wide")
st.title("Assessments")
render_pending_flash()

DIFFICULTY_ICON = {"EASY": "🟢", "MEDIUM": "🟡", "HARD": "🔴"}
FIT_ICON = {"BEST": "🟢", "MEDIUM": "🟡", "NO": "🔴"}

try:
    all_jds = api_client.list_jds()
except requests.RequestException as exc:
    st.error(f"Could not load JDs: {exc}")
    all_jds = []

confirmed_jds = [jd for jd in all_jds if jd["status"] == "CONFIRMED"]
if not confirmed_jds:
    st.info("No confirmed JDs yet. Go confirm a JD and screen some resumes first.")
    st.stop()

jd_labels = {jd["id"]: f"{jd.get('job_title') or jd['filename']} (v{jd['version']})" for jd in confirmed_jds}
selected_jd_id = st.selectbox(
    "JD", options=list(jd_labels.keys()), format_func=lambda i: jd_labels[i], key="assessment_jd_id"
)

try:
    candidates = api_client.get_screening_table(selected_jd_id)
except requests.RequestException as exc:
    st.error(f"Could not load candidates: {exc}")
    candidates = []

if not candidates:
    st.info("No scored candidates yet for this JD - screen some resumes first (Screening Results page).")
    st.stop()

candidates = sorted(candidates, key=lambda c: c.get("overall_rating") or 0, reverse=True)
candidate_labels = {
    c["resume_id"]: f"{FIT_ICON.get(c['fit'], '')} {c.get('name') or 'Unknown'} - {c['fit']} ({c['overall_rating']})"
    for c in candidates
}
selected_resume_id = st.selectbox(
    "Candidate", options=list(candidate_labels.keys()), format_func=lambda i: candidate_labels[i], key="assessment_resume_id"
)

st.divider()

# ---------------------------------------------------------------- generate ---
st.subheader("Generate a new assessment")
st.caption("Questions are targeted at the overlap between this JD's requirements and the candidate's own resume.")

c1, c2, c3 = st.columns(3)
num_easy = c1.number_input("Easy questions", min_value=0, max_value=10, value=2)
num_medium = c2.number_input("Medium questions", min_value=0, max_value=10, value=2)
num_hard = c3.number_input("Hard questions", min_value=0, max_value=10, value=1)

if st.button("🎯 Generate assessment", type="primary", disabled=(num_easy + num_medium + num_hard == 0)):
    with st.spinner("Generating targeted questions..."):
        try:
            assessment = api_client.generate_assessment(selected_resume_id, num_easy, num_medium, num_hard)
            st.session_state["latest_assessment_id"] = assessment["id"]
            flash("success", f"Generated {len(assessment['questions'])} question(s).")
            st.rerun()
        except requests.RequestException as exc:
            st.error(f"Generation failed: {exc}")

st.divider()

# ------------------------------------------------------------------ view -----
try:
    history = api_client.list_assessments(selected_resume_id)
except requests.RequestException as exc:
    st.error(f"Could not load assessment history: {exc}")
    history = []

if not history:
    st.caption("No assessments generated yet for this candidate.")
else:
    default_id = st.session_state.get("latest_assessment_id", history[0]["id"])
    labels = {a["id"]: f"{a['created_at']} - {len(a['questions'])} question(s)" for a in history}
    ids = list(labels.keys())
    default_index = ids.index(default_id) if default_id in ids else 0
    chosen_id = st.selectbox(
        "Assessment (most recent first)", options=ids, format_func=lambda i: labels[i], index=default_index
    )
    chosen = next(a for a in history if a["id"] == chosen_id)
    questions = chosen["questions"]

    st.subheader(f"{len(questions)} question(s)")
    for q in questions:
        with st.expander(
            f"{DIFFICULTY_ICON.get(q['difficulty'], '')} [{q['difficulty']}] {q['skill_tag']}: {q['question'][:80]}"
        ):
            st.write(f"**Question:** {q['question']}")
            st.write(f"**Skill:** {q['skill_tag']}  |  **Difficulty:** {q['difficulty']}")
            st.write("**Expected answer points (interviewer only):**")
            for point in q.get("expected_answer_points") or []:
                st.write(f"- {point}")

    st.divider()
    st.subheader("Export")
    e1, e2, e3 = st.columns(3)
    e1.download_button(
        "⬇️ Interviewer (Markdown)",
        data=interviewer_markdown(questions),
        file_name=f"assessment_{chosen_id}_interviewer.md",
        mime="text/markdown",
        width="stretch",
    )
    e2.download_button(
        "⬇️ Interviewer (CSV)",
        data=interviewer_csv(questions),
        file_name=f"assessment_{chosen_id}_interviewer.csv",
        mime="text/csv",
        width="stretch",
    )
    e3.download_button(
        "⬇️ Candidate version (Markdown)",
        data=candidate_markdown(questions),
        file_name=f"assessment_{chosen_id}_candidate.md",
        mime="text/markdown",
        width="stretch",
        help="Answer points and skill tags stripped - safe to share with the candidate.",
    )
