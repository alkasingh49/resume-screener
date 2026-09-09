"""Thin HTTP client for the FastAPI backend.

This is the ONLY module in the frontend that knows API URLs or calls
`requests` directly - every Streamlit page goes through here. Deliberately
decoupled from `backend.core.config`: the frontend only ever talks to the
backend over HTTP, per the architecture.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
_DEFAULT_TIMEOUT = 10
_LLM_TIMEOUT = 120  # upload/reparse run text + LLM extraction inline (blocking)


def get_health() -> dict:
    """Call GET /health. Raises requests.RequestException if the backend is unreachable."""
    response = requests.get(f"{API_BASE_URL}/health", timeout=_DEFAULT_TIMEOUT)
    response.raise_for_status()
    return response.json()


# --------------------------------------------------------------------- JDs ---


def upload_jd(filename: str, content: bytes, content_type: str | None) -> dict:
    files = {"file": (filename, content, content_type or "application/octet-stream")}
    response = requests.post(f"{API_BASE_URL}/jds/upload", files=files, timeout=_LLM_TIMEOUT)
    response.raise_for_status()
    return response.json()


def list_jds() -> list[dict]:
    response = requests.get(f"{API_BASE_URL}/jds", timeout=_DEFAULT_TIMEOUT)
    response.raise_for_status()
    return response.json()


def get_jd(jd_id: int) -> dict:
    response = requests.get(f"{API_BASE_URL}/jds/{jd_id}", timeout=_DEFAULT_TIMEOUT)
    response.raise_for_status()
    return response.json()


def update_jd(jd_id: int, payload: dict) -> dict:
    response = requests.put(f"{API_BASE_URL}/jds/{jd_id}", json=payload, timeout=_DEFAULT_TIMEOUT)
    response.raise_for_status()
    return response.json()


def confirm_jd(jd_id: int) -> dict:
    response = requests.post(f"{API_BASE_URL}/jds/{jd_id}/confirm", timeout=_DEFAULT_TIMEOUT)
    response.raise_for_status()
    return response.json()


def reparse_jd(jd_id: int) -> dict:
    response = requests.post(f"{API_BASE_URL}/jds/{jd_id}/reparse", timeout=_LLM_TIMEOUT)
    response.raise_for_status()
    return response.json()


def delete_jd(jd_id: int) -> None:
    response = requests.delete(f"{API_BASE_URL}/jds/{jd_id}", timeout=_DEFAULT_TIMEOUT)
    response.raise_for_status()


# ----------------------------------------------------------------- Resumes ---


def upload_resumes(jd_id: int, files: list[tuple[str, bytes, str | None]]) -> dict:
    """`files` is a list of (filename, content, content_type) tuples."""
    payload = [
        ("files", (name, content, content_type or "application/octet-stream"))
        for name, content, content_type in files
    ]
    response = requests.post(
        f"{API_BASE_URL}/resumes/upload", params={"jd_id": jd_id}, files=payload, timeout=_LLM_TIMEOUT
    )
    response.raise_for_status()
    return response.json()


def list_resumes(jd_id: int) -> list[dict]:
    response = requests.get(f"{API_BASE_URL}/resumes", params={"jd_id": jd_id}, timeout=_DEFAULT_TIMEOUT)
    response.raise_for_status()
    return response.json()


def get_resume(resume_id: int) -> dict:
    response = requests.get(f"{API_BASE_URL}/resumes/{resume_id}", timeout=_DEFAULT_TIMEOUT)
    response.raise_for_status()
    return response.json()


def process_resume(resume_id: int) -> dict:
    """Manually (re)run the full parse+score pipeline for one resume -
    a retry tool for a FAILED file. Resumes are processed automatically on
    upload (see run_pipeline_now); this is for catching up a stuck/failed
    one without re-uploading.
    """
    response = requests.post(f"{API_BASE_URL}/resumes/{resume_id}/process", timeout=_LLM_TIMEOUT)
    response.raise_for_status()
    return response.json()


def run_pipeline_now(jd_id: int) -> dict:
    """Manually (re)run the pipeline for every PENDING/FAILED resume under
    one JD - a batch retry tool (e.g. after fixing a missing API key).
    """
    response = requests.post(f"{API_BASE_URL}/resumes/pipeline/run", params={"jd_id": jd_id}, timeout=_LLM_TIMEOUT)
    response.raise_for_status()
    return response.json()


def get_resume_candidate(resume_id: int) -> dict | None:
    """Returns None (not an error) if no candidate profile has been
    extracted yet - callers use this to decide what to show in a status
    table without needing a try/except per row.
    """
    response = requests.get(f"{API_BASE_URL}/resumes/{resume_id}/candidate", timeout=_DEFAULT_TIMEOUT)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def get_screening_result(resume_id: int) -> dict | None:
    """Returns None (not an error) if this resume hasn't been scored yet."""
    response = requests.get(f"{API_BASE_URL}/screening/results/by-resume/{resume_id}", timeout=_DEFAULT_TIMEOUT)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def get_screening_table(jd_id: int) -> list[dict]:
    """One row per scored candidate for `jd_id`, joined with their profile
    fields - what the results dashboard renders.
    """
    response = requests.get(f"{API_BASE_URL}/screening/results/table", params={"jd_id": jd_id}, timeout=_DEFAULT_TIMEOUT)
    response.raise_for_status()
    return response.json()


# ------------------------------------------------------------- Assessments ---


def generate_assessment(resume_id: int, num_easy: int, num_medium: int, num_hard: int) -> dict:
    payload = {"resume_id": resume_id, "num_easy": num_easy, "num_medium": num_medium, "num_hard": num_hard}
    response = requests.post(f"{API_BASE_URL}/assessments/generate", json=payload, timeout=_LLM_TIMEOUT)
    response.raise_for_status()
    return response.json()


def list_assessments(resume_id: int) -> list[dict]:
    response = requests.get(f"{API_BASE_URL}/assessments", params={"resume_id": resume_id}, timeout=_DEFAULT_TIMEOUT)
    response.raise_for_status()
    return response.json()
