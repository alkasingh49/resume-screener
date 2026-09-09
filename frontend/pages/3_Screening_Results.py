"""Results dashboard: ranked candidates for a JD - filter by Fit, sorted by
rating (click a column header to re-sort), search by name/skill, click a
row for the full detail view (profile, scores, reason, resume text),
export CSV/Excel.
"""

import io

import pandas as pd
import requests
import streamlit as st

from services import api_client

st.set_page_config(page_title="Screening Results", page_icon="📊", layout="wide")
st.title("Screening Results")

FIT_ICON = {"BEST": "🟢", "MEDIUM": "🟡", "NO": "🔴"}
FIT_OPTIONS = ["BEST", "MEDIUM", "NO"]

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
    "JD", options=list(jd_labels.keys()), format_func=lambda i: jd_labels[i], key="results_jd_id"
)
try:
    jd = api_client.get_jd(selected_jd_id)  # list_jds() only has the lightweight fields - need must/good-to-have skills
except requests.RequestException as exc:
    st.error(f"Could not load JD details: {exc}")
    st.stop()

try:
    table_rows = api_client.get_screening_table(selected_jd_id)
except requests.RequestException as exc:
    st.error(f"Could not load results: {exc}")
    table_rows = []

if not table_rows:
    st.info("No scored candidates yet for this JD - upload resumes against it on the Upload Resumes page.")
    st.stop()

# ---------------------------------------------------------------- filters ---
f1, f2 = st.columns([1, 2])
fit_filter = f1.multiselect("Fit", options=FIT_OPTIONS, default=FIT_OPTIONS)
search = f2.text_input("Search by name or skill", placeholder="e.g. Ada, or Python")

search_lower = search.strip().lower()


def _matches_search(row: dict) -> bool:
    if not search_lower:
        return True
    if search_lower in (row.get("name") or "").lower():
        return True
    return any(search_lower in skill.lower() for skill in row.get("skills") or [])


filtered = [r for r in table_rows if r.get("fit") in fit_filter and _matches_search(r)]
filtered.sort(key=lambda r: r.get("overall_rating") if r.get("overall_rating") is not None else -1, reverse=True)

st.caption(f"{len(filtered)} of {len(table_rows)} candidate(s) shown")

# ------------------------------------------------------------------ table ---
skill_columns = list(dict.fromkeys((jd.get("must_have_skills") or []) + (jd.get("good_to_have_skills") or [])))
must_have = set(jd.get("must_have_skills") or [])

display_rows = []
for r in filtered:
    row = {
        "Fit": f"{FIT_ICON.get(r['fit'], '')} {r['fit']}" if r.get("fit") else "-",
        "Rating": r.get("overall_rating"),
        "Name": r.get("name") or "Unknown",
        "Email": r.get("email") or "",
        "Phone": r.get("phone") or "",
        "Total Exp": r.get("total_experience_years"),
        "Relevant Exp": r.get("relevant_experience_years"),
    }
    for skill in skill_columns:
        label = f"{skill} (must)" if skill in must_have else f"{skill} (good)"
        row[label] = r.get("per_skill_scores", {}).get(skill, "-")
    row["Reason"] = r.get("reason") or ""
    display_rows.append(row)

df = pd.DataFrame(display_rows)

selection = st.dataframe(
    df,
    width="stretch",
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    key="results_table",
)

# ----------------------------------------------------------------- export ---
e1, e2 = st.columns(2)
e1.download_button(
    "⬇️ Export CSV",
    data=df.to_csv(index=False).encode("utf-8"),
    file_name=f"screening_results_jd{selected_jd_id}.csv",
    mime="text/csv",
    width="stretch",
)
excel_buffer = io.BytesIO()
df.to_excel(excel_buffer, index=False, engine="openpyxl")
e2.download_button(
    "⬇️ Export Excel",
    data=excel_buffer.getvalue(),
    file_name=f"screening_results_jd{selected_jd_id}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    width="stretch",
)

# ----------------------------------------------------------------- detail ---
selected_indices = selection.selection.rows if selection and selection.selection else []
if selected_indices:
    st.divider()
    row = filtered[selected_indices[0]]
    candidate = api_client.get_resume_candidate(row["resume_id"])
    try:
        resume_detail = api_client.get_resume(row["resume_id"])
    except requests.RequestException:
        resume_detail = None

    st.subheader(f"{FIT_ICON.get(row.get('fit'), '')} {row.get('name') or 'Unknown'} - {row.get('fit') or ''}")

    c1, c2, c3 = st.columns(3)
    c1.metric("Overall Rating", row.get("overall_rating"))
    c2.metric("Total Experience (yrs)", row.get("total_experience_years"))
    c3.metric("Relevant Experience (yrs)", row.get("relevant_experience_years"))

    st.markdown(f"**Reason:** {row.get('reason') or '-'}")

    st.markdown("**Per-skill scores**")
    scores = row.get("per_skill_scores") or {}
    if scores:
        st.dataframe(
            pd.DataFrame([{"Skill": k, "Score (0-10)": v} for k, v in scores.items()]),
            hide_index=True,
            width="stretch",
        )

    if candidate:
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Contact**")
            st.write(f"Email: {candidate.get('email') or '-'}")
            st.write(f"Phone: {candidate.get('phone') or '-'}")
            st.write(f"Location: {candidate.get('location') or '-'}")
            st.write(f"Current: {candidate.get('current_title') or '-'} at {candidate.get('current_company') or '-'}")

            st.markdown("**Skills**")
            st.write(", ".join(candidate.get("skills") or []) or "-")

            st.markdown("**Certifications**")
            st.write(", ".join(candidate.get("certifications") or []) or "-")

        with col_b:
            st.markdown("**Education**")
            for edu in candidate.get("education") or []:
                st.write(f"- {edu.get('degree', '')} - {edu.get('institution', '')} ({edu.get('year', '')})")
            if not candidate.get("education"):
                st.write("-")

            st.markdown("**Work History**")
            for w in candidate.get("work_history") or []:
                st.write(
                    f"- {w.get('title', '')} at {w.get('company', '')} "
                    f"({w.get('start_date', '')} - {w.get('end_date') or 'Present'})"
                )
            if not candidate.get("work_history"):
                st.write("-")

    with st.expander("Full resume text"):
        st.text((resume_detail or {}).get("raw_text") or "(not available)")
else:
    st.caption("Click a row above to see the full candidate detail.")
