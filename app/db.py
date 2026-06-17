"""SQLAlchemy engine + session factory (synchronous)."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import config

# pool_pre_ping avoids stale connections after Railway/Postgres idles them out.
engine = create_engine(
    config.require("DATABASE_URL", config.DATABASE_URL),
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Session:
    """Return a new session (caller is responsible for closing)."""
    return SessionLocal()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope: commit on success, rollback on error, always close."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# FastAPI dependency
def db_dependency() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
