"""Pick a confirmed JD, bulk-upload resumes against it, watch per-file status.

No JD selected means no upload allowed. Uploading now automatically queues
the full parse+score pipeline (backend/services/pipeline.py) in the
background - no manual step required. "Retry pending/failed" is a manual
catch-up tool (e.g. after fixing a missing API key or a transient outage),
and "Refresh status" just re-polls since there's still no push-based
update mechanism in this POC.
"""

import requests
import streamlit as st

from components.flash import flash, render_pending_flash
from services import api_client

st.set_page_config(page_title="Upload Resumes", page_icon="📥", layout="wide")
st.title("Upload Resumes")
render_pending_flash()

STATUS_ICON = {
    "PENDING": "⏳",
    "PARSING": "🔎",
    "SCORING": "🧮",
    "DONE": "✅",
    "FAILED": "🔴",
}
FIT_ICON = {"BEST": "🟢", "MEDIUM": "🟡", "NO": "🔴"}

try:
    all_jds = api_client.list_jds()
except requests.RequestException as exc:
    st.error(f"Could not load JDs: {exc}")
    all_jds = []

confirmed_jds = [jd for jd in all_jds if jd["status"] == "CONFIRMED"]

if not confirmed_jds:
    st.info(
        "No confirmed JDs yet. Go to **Job Descriptions**, upload one, review the "
        "extracted fields, and click Confirm before you can upload resumes against it."
    )
    st.stop()

jd_labels = {jd["id"]: f"{jd.get('job_title') or jd['filename']} (v{jd['version']})" for jd in confirmed_jds}
selected_jd_id = st.selectbox(
    "Confirmed JD to screen against",
    options=list(jd_labels.keys()),
    format_func=lambda jd_id: jd_labels[jd_id],
    key="resume_jd_id",
)

st.divider()

# ---------------------------------------------------------------- upload ---
st.subheader("Bulk upload")
uploaded_files = st.file_uploader(
    "Resume files (.pdf .docx .txt .rtf .png .jpg)",
    type=["pdf", "docx", "txt", "rtf", "png", "jpg", "jpeg"],
    accept_multiple_files=True,
)

if st.button("Upload batch", type="primary", disabled=not uploaded_files):
    with st.spinner(f"Storing {len(uploaded_files)} file(s)..."):
        try:
            files = [(f.name, f.getvalue(), f.type) for f in uploaded_files]
            result = api_client.upload_resumes(selected_jd_id, files)
            message = f"Stored {result['uploaded']} file(s)  - parsing and scoring have started in the background."
            if result["failed"]:
                message += f" {result['failed']} rejected immediately (see status below)."
            flash("success" if not result["failed"] else "warning", message)
            st.rerun()
        except requests.RequestException as exc:
            st.error(f"Upload failed: {exc}")

st.divider()

# ------------------------------------------------------------------ list ---
header_col, retry_col, refresh_col = st.columns([3, 1, 1])
header_col.subheader(f"Resumes for: {jd_labels[selected_jd_id]}")
if refresh_col.button("🔄 Refresh status", width="stretch"):
    st.rerun()

try:
    resumes = api_client.list_resumes(selected_jd_id)
except requests.RequestException as exc:
    st.error(f"Could not load resumes: {exc}")
    resumes = []

retryable = [r for r in resumes if r["status"] in ("PENDING", "FAILED")]
if retry_col.button(f"↻ Retry ({len(retryable)})", width="stretch", disabled=not retryable):
    with st.spinner("Running pipeline..."):
        try:
            result = api_client.run_pipeline_now(selected_jd_id)
            flash("success", f"Queued {result['queued']} file(s).")
        except requests.RequestException as exc:
            st.error(f"Retry failed: {exc}")
    st.rerun()

if not resumes:
    st.caption("No resumes uploaded against this JD yet.")
else:
    rows = []
    for r in resumes:
        row = {
            "Status": f"{STATUS_ICON.get(r['status'], '')} {r['status']}",
            "Filename": r["filename"],
            "Candidate": "",
            "Title": "",
            "Total Exp (yrs)": "",
            "Fit": "",
            "Rating": "",
            "Size (KB)": round(r["file_size"] / 1024, 1),
            "Error": r.get("error_message") or "",
        }
        if r["status"] in ("SCORING", "DONE"):
            candidate = api_client.get_resume_candidate(r["id"])
            if candidate:
                row["Candidate"] = candidate.get("name") or ""
                row["Title"] = candidate.get("current_title") or ""
                years = candidate.get("total_experience_years")
                source = candidate.get("total_experience_source")
                if years is not None:
                    row["Total Exp (yrs)"] = f"{years}" + (" (est.)" if source == "LLM_FALLBACK" else "")
        if r["status"] == "DONE":
            result = api_client.get_screening_result(r["id"])
            if result:
                row["Fit"] = f"{FIT_ICON.get(result['fit'], '')} {result['fit']}"
                row["Rating"] = result.get("overall_rating")
        rows.append(row)

    st.dataframe(rows, width="stretch", hide_index=True)

    pending_count = sum(1 for r in resumes if r["status"] in ("PENDING", "PARSING", "SCORING"))
    if pending_count:
        st.caption(f"{pending_count} file(s) still processing - click 'Refresh status' to check progress.")
