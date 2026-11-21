"""Core closed-loop service.

Three heterogeneous interaction paths (workbench visit, API event check-in,
completed SOP task) each write their own business row AND one consolidated
``timeline_event`` row.  Contact recency is *recomputed from timeline data*,
never assigned from the caller's parameter — so removing the consolidation
write would break the recency assertion (no false-green parameter passing).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from . import clock
from .models import (
    Contact,
    Enterprise,
    EventCheckin,
    MemberEvent,
    SopTask,
    TimelineEvent,
    Visit,
)

# Source module labels written onto every timeline row.
SRC_VISIT = "S2-CRM/workbench.visits"
SRC_CHECKIN = "S2-CRM/events.checkin"
SRC_SOP = "S3-SOP/workbench.tasks"

# Jump-link templates. The real source record id is interpolated, so the link
# always points at a concrete artifact rather than a constant placeholder.
LINK_VISIT = "/workbench/visits/{id}"
LINK_CHECKIN = "/workbench/events/{event_id}/checkins/{id}"
LINK_SOP = "/workbench/sop/tasks/{id}"


def _at(moment: datetime | None) -> datetime:
    return moment or clock.utcnow()


def _assert_owned(db: Session, model, object_id: uuid.UUID, org_id: uuid.UUID,
                  site_id: uuid.UUID | None = None) -> None:
    """Defense in depth: a referenced object must belong to the calling tenant.

    In production the tenant comes from the auth context (S2-CRM gateway); here
    request payloads are explicit, so we still verify ownership at the data
    layer rather than trusting a caller-supplied foreign key (no cross-tenant
    IDOR even with stubbed auth).
    """
    conds = [model.id == object_id, model.org_id == org_id,
             model.deleted_at.is_(None)]
    if site_id is not None and hasattr(model, "site_id"):
        conds.append(model.site_id == site_id)
    if db.scalar(select(model.id).where(*conds)) is None:
        raise LookupError(f"{model.__tablename__} not in current tenant scope")


def recompute_contact_recency(db: Session, *, contact_id: uuid.UUID, org_id: uuid.UUID,
                              site_id: uuid.UUID | None = None) -> datetime | None:
    """Recompute a contact's last_interaction_at from persisted timeline rows.

    Uses MAX(occurred_at) across that contact's live timeline events — not the
    last write and not a caller-supplied timestamp.  Scoped by org_id (and
    site_id when supplied) so a cross-tenant row can never influence recency.
    """
    recency_scope = [
        TimelineEvent.contact_id == contact_id,
        TimelineEvent.org_id == org_id,
        TimelineEvent.deleted_at.is_(None),
    ]
    if site_id is not None:
        recency_scope.append(TimelineEvent.site_id == site_id)
    latest = db.scalar(select(func.max(TimelineEvent.occurred_at)).where(*recency_scope))
    contact_scope = [
        Contact.id == contact_id,
        Contact.org_id == org_id,
        Contact.deleted_at.is_(None),
    ]
    if site_id is not None:
        contact_scope.append(Contact.site_id == site_id)
    contact = db.scalar(select(Contact).where(*contact_scope))
    if contact is None:
        raise LookupError("contact not found in current tenant")
    contact.last_interaction_at = latest
    db.flush()
    return latest


def record_visit(
    db: Session,
    *,
    org_id: uuid.UUID,
    site_id: uuid.UUID,
    actor_id: uuid.UUID,
    enterprise_id: uuid.UUID,
    contact_id: uuid.UUID,
    visit_type: str,
    occurred_at: datetime | None = None,
    summary: str = "",
    next_steps: str = "",
) -> dict:
    """Membership manager records a visit in the workbench."""
    _assert_owned(db, Enterprise, enterprise_id, org_id, site_id)
    _assert_owned(db, Contact, contact_id, org_id, site_id)
    when = _at(occurred_at)
    visit = Visit(
        org_id=org_id,
        site_id=site_id,
        created_by=actor_id,
        enterprise_id=enterprise_id,
        contact_id=contact_id,
        visit_type=visit_type,
        occurred_at=when,
        summary=summary,
        next_steps=next_steps,
    )
    db.add(visit)
    db.flush()
    db.add(
        TimelineEvent(
            org_id=org_id,
            site_id=site_id,
            created_by=actor_id,
            enterprise_id=enterprise_id,
            contact_id=contact_id,
            interaction_type="visit",
            occurred_at=when,
            source_module=SRC_VISIT,
            jump_link=LINK_VISIT.format(id=visit.id),
            source_ref_id=visit.id,
            summary=summary,
        )
    )
    db.flush()
    recompute_contact_recency(db, contact_id=contact_id, org_id=org_id, site_id=site_id)
    return {"id": visit.id, "occurred_at": when}


def checkin_event(
    db: Session,
    *,
    org_id: uuid.UUID,
    site_id: uuid.UUID,
    actor_id: uuid.UUID,
    enterprise_id: uuid.UUID,
    contact_id: uuid.UUID,
    event_id: uuid.UUID,
    occurred_at: datetime | None = None,
) -> dict:
    """Simulate a contact checking in to a member-exclusive event via API."""
    _assert_owned(db, Enterprise, enterprise_id, org_id, site_id)
    _assert_owned(db, Contact, contact_id, org_id, site_id)
    _assert_owned(db, MemberEvent, event_id, org_id, site_id)
    when = _at(occurred_at)
    checkin = EventCheckin(
        org_id=org_id,
        site_id=site_id,
        created_by=actor_id,
        enterprise_id=enterprise_id,
        contact_id=contact_id,
        event_id=event_id,
        occurred_at=when,
    )
    db.add(checkin)
    db.flush()
    db.add(
        TimelineEvent(
            org_id=org_id,
            site_id=site_id,
            created_by=actor_id,
            enterprise_id=enterprise_id,
            contact_id=contact_id,
            interaction_type="event_checkin",
            occurred_at=when,
            source_module=SRC_CHECKIN,
            jump_link=LINK_CHECKIN.format(event_id=event_id, id=checkin.id),
            source_ref_id=checkin.id,
            summary="member-exclusive event check-in",
        )
    )
    db.flush()
    recompute_contact_recency(db, contact_id=contact_id, org_id=org_id, site_id=site_id)
    return {"id": checkin.id, "occurred_at": when}


def complete_sop_task(
    db: Session,
    *,
    org_id: uuid.UUID,
    site_id: uuid.UUID,
    actor_id: uuid.UUID,
    task_id: uuid.UUID,
    occurred_at: datetime | None = None,
) -> dict:
    """Membership manager completes a dispatched SOP to-do item."""
    when = _at(occurred_at)
    task = db.scalar(
        select(SopTask).where(
            SopTask.id == task_id,
            SopTask.org_id == org_id,
            SopTask.site_id == site_id,
            SopTask.deleted_at.is_(None),
        )
    )
    if task is None:
        raise LookupError("SOP task not found in current tenant")
    if task.status == "completed":
        raise ValueError("SOP task already completed (idempotency guard)")
    task.status = "completed"
    task.completed_at = when
    db.flush()
    db.add(
        TimelineEvent(
            org_id=org_id,
            site_id=site_id,
            created_by=actor_id,
            enterprise_id=task.enterprise_id,
            contact_id=task.contact_id,
            interaction_type="sop_task",
            occurred_at=when,
            source_module=SRC_SOP,
            jump_link=LINK_SOP.format(id=task.id),
            source_ref_id=task.id,
            summary=f"SOP completed: {task.code}",
        )
    )
    db.flush()
    recompute_contact_recency(
        db, contact_id=task.contact_id, org_id=org_id, site_id=site_id
    )
    return {"id": task.id, "occurred_at": when}


def enterprise_timeline(
    db: Session,
    *,
    org_id: uuid.UUID,
    site_id: uuid.UUID,
    enterprise_id: uuid.UUID,
) -> list[dict]:
    """Return the enterprise timeline in reverse chronological order."""
    rows = db.scalars(
        select(TimelineEvent)
        .where(
            TimelineEvent.org_id == org_id,
            TimelineEvent.site_id == site_id,
            TimelineEvent.enterprise_id == enterprise_id,
            TimelineEvent.deleted_at.is_(None),
        )
        # Tie-break by id so ordering is deterministic even if two rows share
        # an occurred_at value.  Sorting is by interaction time, not insert id.
        .order_by(TimelineEvent.occurred_at.desc(), TimelineEvent.id.desc())
    ).all()
    return [
        {
            "id": str(r.id),
            "interaction_type": r.interaction_type,
            "occurred_at": r.occurred_at.isoformat(),
            "source_module": r.source_module,
            "jump_link": r.jump_link,
            "contact_id": str(r.contact_id),
        }
        for r in rows
    ]


def monthly_active_enterprises(
    db: Session,
    *,
    org_id: uuid.UUID,
    site_id: uuid.UUID,
    year: int,
    month: int,
) -> list[str]:
    """Enterprises with >= 1 valid (live) interaction in the requested month.

    Window is [first of month, first of next month) in UTC.  A control
    enterprise whose only interactions fall in the previous month is excluded.
    """
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    rows = db.execute(
        select(TimelineEvent.enterprise_id)
        .distinct()
        .where(
            TimelineEvent.org_id == org_id,
            TimelineEvent.site_id == site_id,
            TimelineEvent.deleted_at.is_(None),
            TimelineEvent.occurred_at >= start,
            TimelineEvent.occurred_at < end,
        )
        .order_by(TimelineEvent.enterprise_id)
    ).scalars().all()
    return [str(r) for r in rows]
