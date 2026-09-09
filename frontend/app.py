"""Streamlit shell - home page and backend connectivity check.

Run with: streamlit run frontend/app.py
Feature pages live under frontend/pages/ (Streamlit's multipage convention).
"""

import requests
import streamlit as st

from services.api_client import API_BASE_URL, get_health

st.set_page_config(page_title="AI Resume Screener", page_icon="🧑‍💻", layout="wide")

st.title("AI Resume Screening & Assessment Platform")
st.caption("Talent Acquisition demo - JD intake, bulk resume screening, and assessment generation.")

st.markdown(
    """
    Use the sidebar to navigate:
    1. **Job Descriptions** - upload a JD, review the extracted fields, confirm it
    2. **Upload Resumes** - pick a confirmed JD, bulk-upload candidate resumes
    3. **Screening Results** - ranked candidates with fit, scores, and reasons
    4. **Assessments** - generate and export a tailored technical assessment
    """
)

st.divider()
st.subheader("Backend connectivity")
st.caption(f"API base URL: `{API_BASE_URL}`")

if st.button("Check backend health"):
    try:
        payload = get_health()
        st.success(f"Backend reachable - {payload}")
    except requests.RequestException as exc:
        st.error(f"Could not reach backend: {exc}")
