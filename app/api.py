"""FastAPI application exposing the three interaction paths and read models.

All endpoints take org_id/site_id explicitly so tenant scoping is visible and
testable (critic:safety — no cross-tenant IDOR).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import service
from .db import make_session_factory

app = FastAPI(title="Enterprise Timeline Closed Loop (fictional test data)")
SessionFactory = None  # bound in tests / runtime via bind_engine


def bind_engine(engine) -> None:
    global SessionFactory
    SessionFactory = make_session_factory(engine)


def _session() -> Session:
    if SessionFactory is None:
        raise RuntimeError("engine not bound; call bind_engine() first")
    return SessionFactory()


class VisitIn(BaseModel):
    org_id: uuid.UUID
    site_id: uuid.UUID
    actor_id: uuid.UUID
    enterprise_id: uuid.UUID
    contact_id: uuid.UUID
    visit_type: str = Field(min_length=1)
    occurred_at: datetime | None = None
    summary: str = ""
    next_steps: str = ""


class CheckinIn(BaseModel):
    org_id: uuid.UUID
    site_id: uuid.UUID
    actor_id: uuid.UUID
    enterprise_id: uuid.UUID
    contact_id: uuid.UUID
    event_id: uuid.UUID
    occurred_at: datetime | None = None


class SopIn(BaseModel):
    org_id: uuid.UUID
    site_id: uuid.UUID
    actor_id: uuid.UUID
    task_id: uuid.UUID
    occurred_at: datetime | None = None


@app.post("/interactions/visit", status_code=201)
def api_visit(payload: VisitIn):
    db = _session()
    try:
        result = service.record_visit(
            db,
            org_id=payload.org_id,
            site_id=payload.site_id,
            actor_id=payload.actor_id,
            enterprise_id=payload.enterprise_id,
            contact_id=payload.contact_id,
            visit_type=payload.visit_type,
            occurred_at=payload.occurred_at,
            summary=payload.summary,
            next_steps=payload.next_steps,
        )
        db.commit()
        return {"ok": True, "id": str(result["id"]), "type": "visit"}
    finally:
        db.close()


@app.post("/interactions/event-checkin", status_code=201)
def api_checkin(payload: CheckinIn):
    db = _session()
    try:
        result = service.checkin_event(
            db,
            org_id=payload.org_id,
            site_id=payload.site_id,
            actor_id=payload.actor_id,
            enterprise_id=payload.enterprise_id,
            contact_id=payload.contact_id,
            event_id=payload.event_id,
            occurred_at=payload.occurred_at,
        )
        db.commit()
        return {"ok": True, "id": str(result["id"]), "type": "event_checkin"}
    finally:
        db.close()


@app.post("/interactions/sop-complete", status_code=201)
def api_sop(payload: SopIn):
    db = _session()
    try:
        result = service.complete_sop_task(
            db,
            org_id=payload.org_id,
            site_id=payload.site_id,
            actor_id=payload.actor_id,
            task_id=payload.task_id,
            occurred_at=payload.occurred_at,
        )
        db.commit()
        return {"ok": True, "id": str(result["id"]), "type": "sop_task"}
    finally:
        db.close()


@app.get("/enterprises/{enterprise_id}/timeline")
def api_timeline(
    enterprise_id: uuid.UUID,
    org_id: uuid.UUID = Query(...),
    site_id: uuid.UUID = Query(...),
):
    db = _session()
    try:
        return {
            "enterprise_id": str(enterprise_id),
            "records": service.enterprise_timeline(
                db,
                org_id=org_id,
                site_id=site_id,
                enterprise_id=enterprise_id,
            ),
        }
    finally:
        db.close()


@app.get("/contacts/{contact_id}")
def api_contact(
    contact_id: uuid.UUID,
    org_id: uuid.UUID = Query(...),
    site_id: uuid.UUID | None = Query(None),
):
    from sqlalchemy import select as _select
    from .models import Contact

    db = _session()
    try:
        scope = [
            Contact.id == contact_id,
            Contact.org_id == org_id,
            Contact.deleted_at.is_(None),
        ]
        if site_id is not None:
            scope.append(Contact.site_id == site_id)
        c = db.scalar(_select(Contact).where(*scope))
        if c is None:
            raise HTTPException(status_code=404, detail="contact not found")
        return {
            "id": str(c.id),
            "enterprise_id": str(c.enterprise_id),
            "last_interaction_at": (
                c.last_interaction_at.isoformat() if c.last_interaction_at else None
            ),
        }
    finally:
        db.close()


@app.get("/metrics/monthly-active")
def api_monthly_active(
    org_id: uuid.UUID = Query(...),
    site_id: uuid.UUID = Query(...),
    year: int = Query(...),
    month: int = Query(...),
):
    db = _session()
    try:
        ids = service.monthly_active_enterprises(
            db, org_id=org_id, site_id=site_id, year=year, month=month
        )
        return {"year": year, "month": month, "enterprise_ids": ids}
    finally:
        db.close()
