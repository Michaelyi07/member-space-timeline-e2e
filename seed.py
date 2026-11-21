"""Reusable control-data seed script (delivered artifact).

Produces ONLY fictional data:
  * target enterprise + 2 contacts + 1 member-exclusive event + 1 dispatched
    "Onboarding Follow-up" (入会回访) SOP to-do;
  * a control enterprise whose single interaction is in the PREVIOUS month.

Usage:
    DATABASE_URL=... python seed.py            # print ids as JSON
    DATABASE_URL=... python seed.py --emit-json
"""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import clock
from app.models import (
    Base,
    Contact,
    Enterprise,
    EventCheckin,
    MemberEvent,
    SopTask,
    TimelineEvent,
    Visit,
)
from app import service
from app.config import Settings

ORG = uuid.UUID("00000000-0000-0000-0000-000000000010")
SITE = uuid.UUID("00000000-0000-0000-0000-000000000011")
ACTOR = uuid.UUID("00000000-0000-0000-0000-000000000012")


def seed_all(db, *, now: datetime) -> dict:
    """Idempotently seed fixtures; returns all ids needed by the test flow."""
    db.add(
        Enterprise(
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            org_id=ORG,
            site_id=SITE,
            created_by=ACTOR,
            name="Fictional Target Enterprise",
        )
    )
    db.add(
        Enterprise(
            id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
            org_id=ORG,
            site_id=SITE,
            created_by=ACTOR,
            name="Fictional Control Enterprise (prior month only)",
        )
    )
    db.flush()

    c1 = uuid.UUID("00000000-0000-0000-0000-000000000101")
    c2 = uuid.UUID("00000000-0000-0000-0000-000000000102")
    db.add(Contact(id=c1, org_id=ORG, site_id=SITE, created_by=ACTOR,
                   enterprise_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                   name="Fictional Contact A"))
    db.add(Contact(id=c2, org_id=ORG, site_id=SITE, created_by=ACTOR,
                   enterprise_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                   name="Fictional Contact B"))
    db.flush()

    event_id = uuid.UUID("00000000-0000-0000-0000-000000000201")
    db.add(MemberEvent(id=event_id, org_id=ORG, site_id=SITE, created_by=ACTOR,
                       title="Fictional Member-Exclusive Event",
                       starts_at=now, ticket_price_cents=0))
    db.flush()

    sop_id = uuid.UUID("00000000-0000-0000-0000-000000000301")
    db.add(SopTask(id=sop_id, org_id=ORG, site_id=SITE, created_by=ACTOR,
                   enterprise_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                   contact_id=c1, code="ONBOARDING_FOLLOWUP",
                   status="open", due_at=now + timedelta(days=3)))

    # Control enterprise: one interaction in the PREVIOUS month only.
    prev = (now.replace(day=1) - timedelta(days=1)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    ctrl_contact = uuid.UUID("00000000-0000-0000-0000-000000000103")
    db.add(Contact(id=ctrl_contact, org_id=ORG, site_id=SITE, created_by=ACTOR,
                   enterprise_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
                   name="Fictional Control Contact"))
    db.flush()
    v = Visit(id=uuid.uuid4(), org_id=ORG, site_id=SITE, created_by=ACTOR,
              enterprise_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
              contact_id=ctrl_contact, visit_type="phone", occurred_at=prev,
              summary="prior-month control", next_steps="")
    db.add(v)
    db.flush()
    db.add(TimelineEvent(
        id=uuid.uuid4(), org_id=ORG, site_id=SITE, created_by=ACTOR,
        enterprise_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        contact_id=ctrl_contact, interaction_type="visit", occurred_at=prev,
        source_module=service.SRC_VISIT, jump_link=service.LINK_VISIT.format(id=v.id),
        source_ref_id=v.id, summary="prior-month control"))
    service.recompute_contact_recency(db, contact_id=ctrl_contact, org_id=ORG)
    db.flush()

    return {
        "org_id": str(ORG),
        "site_id": str(SITE),
        "actor_id": str(ACTOR),
        "target_enterprise_id": "00000000-0000-0000-0000-000000000001",
        "control_enterprise_id": "00000000-0000-0000-0000-000000000002",
        "contact_a": str(c1),
        "contact_b": str(c2),
        "control_contact": str(ctrl_contact),
        "event_id": str(event_id),
        "sop_task_id": str(sop_id),
        "control_interaction_at": prev.isoformat(),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit-json", action="store_true")
    ap.parse_args()
    settings = Settings.from_env()
    engine = create_engine(settings.database_url, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    try:
        ids = seed_all(db, now=clock.utcnow())
        db.commit()
        print(json.dumps(ids, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
