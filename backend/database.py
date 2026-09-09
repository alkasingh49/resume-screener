"""SQLite engine and session helpers.

No migration tool: this is a demo, so `init_db()` just creates whatever
tables don't exist yet.
"""

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


@lru_cache
def _engine() -> Engine:
    from .config import get_settings

    url = get_settings().DATABASE_URL
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


@lru_cache
def _sessionmaker() -> sessionmaker:
    return sessionmaker(bind=_engine(), autoflush=False, autocommit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    db = _sessionmaker()()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session() -> Iterator[Session]:
    """For background work, which has no request to hang a session off."""
    db = _sessionmaker()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  registers the tables on Base.metadata

    Base.metadata.create_all(bind=_engine())
