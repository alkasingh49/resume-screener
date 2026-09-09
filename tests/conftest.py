"""Shared fixtures. An isolated temp SQLite DB and temp upload dirs per test
that touches the DB - opt in with the `isolated_db` fixture.
"""

import pytest

from backend.core.config import get_settings
from backend.db.session import get_engine, get_sessionmaker, init_db


@pytest.fixture
def isolated_db(monkeypatch, tmp_path):
    """Point DATABASE_URL and the upload dirs at a throwaway tmp_path so
    tests never write into the real project's data/ directory, and
    (re)create all tables.
    """
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("UPLOAD_DIR_JDS", str(tmp_path / "uploads" / "jds"))
    monkeypatch.setenv("UPLOAD_DIR_RESUMES", str(tmp_path / "uploads" / "resumes"))
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / "chroma"))
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()

    init_db()
    yield

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
