"""Tests for the Phase 10 error-handling polish: the global unhandled-
exception handler, and the startup config validation warning.
"""

import logging

import pytest
from fastapi.testclient import TestClient

import backend.main as main_module
from backend.main import app

# raise_server_exceptions=False is required here: TestClient's default
# behaviour is to re-raise an unhandled exception into the test process
# rather than let the registered exception handler produce a response -
# fine for normal tests (a real bug should fail loudly), but this file is
# specifically testing what the client actually receives over HTTP.
client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _db(isolated_db):
    pass


def test_unhandled_exception_returns_clean_500_not_a_raw_traceback(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("something genuinely unexpected")

    monkeypatch.setattr("backend.api.v1.routes.jd.storage.list_jds", _boom)

    response = client.get("/api/v1/jds")
    assert response.status_code == 500
    body = response.json()
    assert body == {"detail": "Internal server error"}
    # the real exception message/traceback must never reach the client
    assert "genuinely unexpected" not in response.text
    assert "RuntimeError" not in response.text


def test_known_failure_modes_are_unaffected_by_the_catch_all():
    """A normal, already-handled 404 should look exactly as it did before -
    the catch-all must not swallow or reshape routes' own error handling.
    """
    response = client.get("/api/v1/jds/9999")
    assert response.status_code == 404
    assert response.json()["detail"] == "JD not found"


def test_validate_llm_config_warns_when_configured_providers_key_is_missing(monkeypatch, caplog):
    # backend.main.settings is bound once at import time (not re-read from
    # get_settings() on every call), so the way to exercise this function
    # with different config is to swap that module attribute directly.
    fake_settings = main_module.settings.model_copy(
        update={"LLM_PROVIDER": "gemini", "EMBEDDING_PROVIDER": "gemini", "GOOGLE_API_KEY": None}
    )
    monkeypatch.setattr(main_module, "settings", fake_settings)

    with caplog.at_level(logging.WARNING):
        main_module._validate_llm_config()

    assert any("LLM_PROVIDER=gemini" in r.message for r in caplog.records)
    assert any("EMBEDDING_PROVIDER=gemini" in r.message for r in caplog.records)


def test_validate_llm_config_silent_when_key_is_present(monkeypatch, caplog):
    fake_settings = main_module.settings.model_copy(
        update={"LLM_PROVIDER": "gemini", "EMBEDDING_PROVIDER": "gemini", "GOOGLE_API_KEY": "a-real-looking-key"}
    )
    monkeypatch.setattr(main_module, "settings", fake_settings)

    with caplog.at_level(logging.WARNING):
        main_module._validate_llm_config()

    assert not caplog.records
