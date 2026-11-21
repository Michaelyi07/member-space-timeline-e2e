"""Alembic env: DSN from DATABASE_URL (env only)."""
from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine

from app.models import Base

config = context.config


def _url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL must be provided via environment")
    return url


def run_migrations_online():
    connectable = create_engine(_url(), future=True)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


run_migrations_online()
