"""Engine/session setup.

Engine and sessionmaker are built lazily and cached (mirrors
`core.config.get_settings`) rather than at import time, so tests can point
`DATABASE_URL` at a temp file and rebuild them mid-run.

No migration tool (Alembic) for this POC - `init_db()` just
`create_all`s whatever tables don't exist yet.
"""

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.core.config import get_settings
from backend.db.base import Base


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
    engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)

    if settings.DATABASE_URL.startswith("sqlite"):
        # SQLite ignores FK constraints unless told otherwise per-connection.
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


@lru_cache
def get_sessionmaker() -> sessionmaker:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency - `Depends(get_db)`. Closes the session after the request."""
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """For use outside a request (scripts, the LLM wrapper's cache/log writes)."""
    db = get_sessionmaker()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Create any tables that don't exist yet. Safe to call more than once."""
    import backend.db.models  # noqa: F401  registers every model on Base.metadata

    Base.metadata.create_all(bind=get_engine())
