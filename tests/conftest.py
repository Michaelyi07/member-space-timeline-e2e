"""pytest fixtures — REAL PostgreSQL 16, never SQLite.

DATABASE_URL comes from the environment.  A fresh, isolated set of tables is
created at session scope; every test truncates the business tables first so the
three-interaction scenario always starts from the seeded precondition.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app import api, clock, models
from app.config import Settings
from seed import ORG, SITE, ACTOR, seed_all

TARGET = uuid.UUID("00000000-0000-0000-0000-000000000001")
CONTROL = uuid.UUID("00000000-0000-0000-0000-000000000002")
CONTACT_A = uuid.UUID("00000000-0000-0000-0000-000000000101")
CONTACT_B = uuid.UUID("00000000-0000-0000-0000-000000000102")
EVENT = uuid.UUID("00000000-0000-0000-0000-000000000201")
SOP = uuid.UUID("00000000-0000-0000-0000-000000000301")
# Frozen "current" moment: 2026-11-15 10:00 UTC — mid current month, so a
# prior-month (2026-10) control interaction is cleanly excluded.
FROZEN_NOW = datetime(2026, 11, 15, 10, 0, 0, tzinfo=timezone.utc)

TABLES = [
    "timeline_event", "event_checkin", "visit", "sop_task",
    "member_event", "contact", "enterprise",
]


@pytest.fixture(scope="session")
def engine():
    url = os.environ["DATABASE_URL"]
    eng = create_engine(url, pool_pre_ping=True, future=True)
    models.Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    s = Session()
    try:
        with engine.begin() as conn:
            conn.execute(
                text("TRUNCATE TABLE " + ", ".join(TABLES) + " RESTART IDENTITY CASCADE")
            )
        clock.freeze(FROZEN_NOW)
        ids = seed_all(s, now=FROZEN_NOW)
        s.commit()
        yield s, ids
    finally:
        s.close()
        clock.unfreeze()


@pytest.fixture()
def client(engine, db):
    # TestClient subclasses httpx.Client (pytest + httpx framework as required).
    api.bind_engine(engine)
    c = TestClient(api.app, base_url="http://testserver")
    try:
        yield c
    finally:
        c.close()
