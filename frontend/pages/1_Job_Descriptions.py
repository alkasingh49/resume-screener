"""JD upload, review, and confirm."""

import requests
import streamlit as st

from components.flash import flash, render_pending_flash
from services import api_client

st.set_page_config(page_title="Job Descriptions", page_icon="📄", layout="wide")
st.title("Job Descriptions")
render_pending_flash()

STATUS_ICON = {
    "UPLOADED": "🔵",
    "PARSED": "🟢",
    "NEEDS_REVIEW": "🟠",
    "CONFIRMED": "✅",
    "FAILED": "🔴",
}


def _skills_to_text(skills: list[str]) -> str:
    return "\n".join(skills or [])


def _text_to_skills(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


# ---------------------------------------------------------------- upload ---
with st.expander("Upload a new JD", expanded=not st.session_state.get("selected_jd_id")):
    uploaded = st.file_uploader(
        "JD file (.pdf .docx .txt .rtf .png .jpg)",
        type=["pdf", "docx", "txt", "rtf", "png", "jpg", "jpeg"],
    )
    if st.button("Upload & parse", type="primary", disabled=uploaded is None):
        with st.spinner("Extracting text and asking the LLM to pull out requirements..."):
            try:
                jd = api_client.upload_jd(uploaded.name, uploaded.getvalue(), uploaded.type)
                st.session_state["selected_jd_id"] = jd["id"]
                if jd["status"] == "FAILED":
                    flash("error", f"Parsing failed: {jd.get('error_message')}")
                else:
                    flash("success", f"Parsed '{jd['filename']}' - status: {jd['status']}")
                st.rerun()
            except requests.RequestException as exc:
                st.error(f"Upload failed: {exc}")

st.divider()

col_list, col_detail = st.columns([1, 2])

# ------------------------------------------------------------------ list ---
with col_list:
    st.subheader("All JDs")
    try:
        jds = api_client.list_jds()
    except requests.RequestException as exc:
        st.error(f"Could not load JDs: {exc}")
        jds = []

    if not jds:
        st.caption("No JDs uploaded yet.")

    for jd_item in jds:
        label = f"{STATUS_ICON.get(jd_item['status'], '')} {jd_item.get('job_title') or jd_item['filename']} (v{jd_item['version']})"
        if st.button(label, key=f"select_{jd_item['id']}", width="stretch"):
            st.session_state["selected_jd_id"] = jd_item["id"]
            st.rerun()

# ---------------------------------------------------------------- detail ---
with col_detail:
    jd_id = st.session_state.get("selected_jd_id")
    if jd_id is None:
        st.info("Select a JD on the left, or upload a new one above.")
    else:
        try:
            jd = api_client.get_jd(jd_id)
        except requests.RequestException as exc:
            st.error(f"Could not load JD {jd_id}: {exc}")
            jd = None

        if jd:
            st.subheader(jd["filename"])
            st.write(
                f"Status: {STATUS_ICON.get(jd['status'], '')} **{jd['status']}**  |  Version: {jd['version']}"
            )
            if jd["status"] == "FAILED":
                st.error(jd.get("error_message") or "Parsing failed.")

            edited = jd.get("edited_fields") or {}

            def _label(field: str, text: str) -> str:
                return f"{text}  ✏️ *edited*" if edited.get(field) else text

            is_confirmed = jd["status"] == "CONFIRMED"

            with st.form(f"jd_form_{jd_id}"):
                job_title = st.text_input(_label("job_title", "Job title"), value=jd.get("job_title") or "")

                c1, c2 = st.columns(2)
                department = c1.text_input(
                    _label("department", "Department"), value=jd.get("department") or ""
                )
                location = c2.text_input(_label("location", "Location"), value=jd.get("location") or "")

                c3, c4, c5 = st.columns(3)
                employment_type = c3.text_input(
                    _label("employment_type", "Employment type"), value=jd.get("employment_type") or ""
                )
                min_years = c4.number_input(
                    _label("min_years", "Min years"),
                    value=float(jd.get("min_years") or 0),
                    min_value=0.0,
                    step=0.5,
                )
                max_years = c5.number_input(
                    _label("max_years", "Max years"),
                    value=float(jd.get("max_years") or 0),
                    min_value=0.0,
                    step=0.5,
                )

                must_have = st.text_area(
                    _label("must_have_skills", "Must-have skills (one per line)"),
                    value=_skills_to_text(jd.get("must_have_skills")),
                    height=100,
                )
                good_to_have = st.text_area(
                    _label("good_to_have_skills", "Good-to-have skills (one per line)"),
                    value=_skills_to_text(jd.get("good_to_have_skills")),
                    height=80,
                )
                responsibilities = st.text_area(
                    _label("key_responsibilities", "Key responsibilities (one per line)"),
                    value=_skills_to_text(jd.get("key_responsibilities")),
                    height=120,
                )
                qualifications = st.text_area(
                    _label("qualifications", "Qualifications"),
                    value=jd.get("qualifications") or "",
                    height=80,
                )

                b1, b2, b3, b4 = st.columns(4)
                save_clicked = b1.form_submit_button("💾 Save")
                confirm_clicked = b2.form_submit_button("✅ Confirm", disabled=is_confirmed)
                reparse_clicked = b3.form_submit_button("🔄 Re-parse", disabled=is_confirmed)
                delete_clicked = b4.form_submit_button("🗑️ Delete")

            payload = {
                "job_title": job_title or None,
                "department": department or None,
                "location": location or None,
                "employment_type": employment_type or None,
                "min_years": min_years or None,
                "max_years": max_years or None,
                "must_have_skills": _text_to_skills(must_have),
                "good_to_have_skills": _text_to_skills(good_to_have),
                "key_responsibilities": _text_to_skills(responsibilities),
                "qualifications": qualifications or None,
            }

            if save_clicked:
                try:
                    api_client.update_jd(jd_id, payload)
                    flash("success", "Saved.")
                    st.rerun()
                except requests.RequestException as exc:
                    st.error(f"Save failed: {exc}")

            if confirm_clicked:
                try:
                    api_client.update_jd(jd_id, payload)  # persist edits, then confirm
                    api_client.confirm_jd(jd_id)
                    flash("success", "Confirmed - it can now be selected for resume screening.")
                    st.rerun()
                except requests.RequestException as exc:
                    detail = exc.response.json().get("detail") if exc.response is not None else str(exc)
                    st.error(f"Confirm failed: {detail}")

            if reparse_clicked:
                with st.spinner("Re-parsing..."):
                    try:
                        api_client.reparse_jd(jd_id)
                        flash("success", "Re-parsed.")
                        st.rerun()
                    except requests.RequestException as exc:
                        st.error(f"Re-parse failed: {exc}")

            if delete_clicked:
                try:
                    api_client.delete_jd(jd_id)
                    del st.session_state["selected_jd_id"]
                    flash("success", "Deleted.")
                    st.rerun()
                except requests.RequestException as exc:
                    st.error(f"Delete failed: {exc}")

            with st.expander("Raw extracted text"):
                st.text(jd.get("raw_text") or "(none)")
