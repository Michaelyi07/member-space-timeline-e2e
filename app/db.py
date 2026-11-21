"""Engine / session factory. DSN is read from DATABASE_URL (env only)."""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL must be provided via environment")
    return url


def make_engine(url: str | None = None):
    return create_engine(url or database_url(), pool_pre_ping=True, future=True)


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
