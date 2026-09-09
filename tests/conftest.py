"""Test fixtures: a throwaway SQLite file and upload dir per test run."""

import pytest


@pytest.fixture(autouse=True)
def temp_env(tmp_path, monkeypatch):
    """Point the app at a temp DB/upload dir, and reset the cached settings,
    engine and sessionmaker so each test gets a clean database."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-used")

    from backend import config, database

    for cached in (config.get_settings, database._engine, database._sessionmaker):
        cached.cache_clear()

    database.init_db()
    yield

    for cached in (config.get_settings, database._engine, database._sessionmaker):
        cached.cache_clear()


@pytest.fixture
def client(temp_env):
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as c:
        yield c
