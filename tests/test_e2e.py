"""E2E tests — pytest + httpx against FastAPI on REAL PostgreSQL 16.

Acceptance criteria
  C1  timeline: 3 records, types visit/event_checkin/sop_task, reverse-chronological
  C2  contact.last_interaction_at equals the most recent interaction time
  C3  monthly-active includes target enterprise, excludes prior-month control
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import httpx

from conftest import (
    ACTOR, CONTACT_A, CONTACT_B, CONTROL, EVENT, ORG, SITE, SOP, TARGET,
)

T1 = datetime(2026, 11, 15, 9, 5, tzinfo=timezone.utc)   # visit
T2 = datetime(2026, 11, 15, 9, 10, tzinfo=timezone.utc)  # check-in
T3 = datetime(2026, 11, 15, 9, 15, tzinfo=timezone.utc)  # SOP done


def _visit(c: httpx.Client, when: datetime, contact=CONTACT_A, etype="in_person"):
    return c.post("/interactions/visit", json={
        "org_id": str(ORG), "site_id": str(SITE), "actor_id": str(ACTOR),
        "enterprise_id": str(TARGET), "contact_id": str(contact),
        "visit_type": etype, "occurred_at": when.isoformat(),
        "summary": "Fictional visit", "next_steps": "Fictional follow-up",
    })


def _checkin(c: httpx.Client, when: datetime, contact=CONTACT_A):
    return c.post("/interactions/event-checkin", json={
        "org_id": str(ORG), "site_id": str(SITE), "actor_id": str(ACTOR),
        "enterprise_id": str(TARGET), "contact_id": str(contact),
        "event_id": str(EVENT), "occurred_at": when.isoformat(),
    })


def _sop(c: httpx.Client, when: datetime):
    return c.post("/interactions/sop-complete", json={
        "org_id": str(ORG), "site_id": str(SITE), "actor_id": str(ACTOR),
        "task_id": str(SOP), "occurred_at": when.isoformat(),
    })


def _timeline(c: httpx.Client, enterprise=TARGET):
    return c.get(f"/enterprises/{enterprise}/timeline",
                 params={"org_id": str(ORG), "site_id": str(SITE)})


def _contact(c: httpx.Client, contact):
    return c.get(f"/contacts/{contact}", params={"org_id": str(ORG)})


def _drive_all(c: httpx.Client, visit_at=T1, checkin_at=T2, sop_at=T3,
               visit_first=True):
    """Drive the three interaction paths; visit_first toggles insertion order."""
    if visit_first:
        steps = [
            ("visit", lambda: _visit(c, visit_at)),
            ("event_checkin", lambda: _checkin(c, checkin_at)),
            ("sop_task", lambda: _sop(c, sop_at)),
        ]
    else:
        # reverse insertion: SOP first, visit last — proves ordering is by time.
        steps = [
            ("sop_task", lambda: _sop(c, sop_at)),
            ("event_checkin", lambda: _checkin(c, checkin_at)),
            ("visit", lambda: _visit(c, visit_at)),
        ]
    for name, fn in steps:
        r = fn()
        assert r.status_code == 201, (name, r.status_code, r.text)
        assert r.json()["ok"] is True


# --------------------------------------------------------------------------
# C1 — timeline type + order
# --------------------------------------------------------------------------
def test_c1_timeline_types_and_reverse_chronological(client, db):
    _drive_all(client)
    resp = _timeline(client)
    assert resp.status_code == 200, resp.text
    recs = resp.json()["records"]

    # exactly 3 records, one per source type
    assert len(recs) == 3
    assert {r["interaction_type"] for r in recs} == {
        "visit", "event_checkin", "sop_task"
    }
    # reverse chronological: newest first
    times = [datetime.fromisoformat(r["occurred_at"]) for r in recs]
    assert times == sorted(times, reverse=True), times
    assert [r["interaction_type"] for r in recs] == [
        "sop_task", "event_checkin", "visit"
    ]


def test_c1_every_record_has_source_module_and_jump_link(client, db):
    _drive_all(client)
    recs = _timeline(client).json()["records"]
    assert len(recs) == 3
    for r in recs:
        assert r["source_module"], r
        assert "/" in r["jump_link"] and r["jump_link"].startswith("/"), r
        # jump link embeds a concrete source id (not a constant placeholder)
        assert r["jump_link"].rstrip("/").split("/")[-1] != "{id}", r
    assert len({r["jump_link"] for r in recs}) == 3, "jump links must be distinct"


def test_c1_ordering_is_time_based_not_insertion_based(client, db):
    """Reinsert in reverse order (SOP first, visit last); timeline still time-sorted."""
    _drive_all(client, visit_first=False)
    recs = _timeline(client).json()["records"]
    assert [r["interaction_type"] for r in recs] == [
        "sop_task", "event_checkin", "visit"
    ], "ordering must follow occurred_at, not insert order"


def test_c1_literal_enum_order_when_times_are_visit_newest(client, db):
    """Alternate time distribution: visit newest -> displayed order visit/checkin/sop.

    Covers the reading of the brief that lists types as visit, event_checkin,
    sop_task in displayed (reverse-chronological) order.
    """
    _drive_all(client, visit_at=T3, checkin_at=T2, sop_at=T1)
    recs = _timeline(client).json()["records"]
    assert [r["interaction_type"] for r in recs] == [
        "visit", "event_checkin", "sop_task"
    ]
    times = [datetime.fromisoformat(r["occurred_at"]) for r in recs]
    assert times == sorted(times, reverse=True)


def test_c1_multi_contact_rolls_up_without_overwriting_recency(client, db):
    """Different contacts' interactions roll up to enterprise view; per-contact
    recency stays independent (no cross-contact overwrite)."""
    assert _visit(c=client, when=T1, contact=CONTACT_B, etype="phone").status_code == 201
    assert _visit(c=client, when=T2, contact=CONTACT_A).status_code == 201
    recs = _timeline(client).json()["records"]
    assert len(recs) == 2  # enterprise view aggregates both contacts
    a = _contact(client, CONTACT_A).json()["last_interaction_at"]
    b = _contact(client, CONTACT_B).json()["last_interaction_at"]
    assert datetime.fromisoformat(a) == T2
    assert datetime.fromisoformat(b) == T1


# --------------------------------------------------------------------------
# C2 — last_interaction_at equals latest interaction time
# --------------------------------------------------------------------------
def test_c2_recency_updates_each_step_and_equals_latest(client, db):
    # step 1: visit at T1
    assert _visit(client, T1).status_code == 201
    assert datetime.fromisoformat(_contact(client, CONTACT_A).json()[
        "last_interaction_at"]) == T1
    # step 2: check-in at T2 (later)
    assert _checkin(client, T2).status_code == 201
    assert datetime.fromisoformat(_contact(client, CONTACT_A).json()[
        "last_interaction_at"]) == T2
    # step 3: SOP done at T3 (latest)
    assert _sop(client, T3).status_code == 201
    final = datetime.fromisoformat(_contact(client, CONTACT_A).json()[
        "last_interaction_at"])
    assert final == T3
    latest_timeline = datetime.fromisoformat(_timeline(client).json()["records"][0][
        "occurred_at"])
    assert final == latest_timeline, "recency must equal newest timeline interaction"


def test_c2_recency_never_regresses_on_out_of_order_writes(client, db):
    """A *later API call* carrying an *earlier* timestamp must NOT roll back
    recency. This kills the false-green implementation 'write the caller's
    occurred_at straight into contact.last_interaction_at': under that bug the
    final value would incorrectly drop to T1.
    """
    assert _visit(client, T3).status_code == 201          # newest first
    assert datetime.fromisoformat(_contact(client, CONTACT_A).json()[
        "last_interaction_at"]) == T3
    # A check-in is written afterwards but its interaction time is earlier.
    assert _checkin(client, T1).status_code == 201
    final = datetime.fromisoformat(_contact(client, CONTACT_A).json()[
        "last_interaction_at"])
    assert final == T3, "recency = MAX of timeline data, not the last write's parameter"


def test_c2_recency_is_sourced_from_timeline_rows(client, db):
    """Removing the newest timeline row and re-driving the recency computation
    through the same service the API uses must make recency fall back — proving
    the value is derived from persisted timeline rows, not a stale constant.
    """
    from app import service
    from app.api import SessionFactory
    from app.models import TimelineEvent
    assert _visit(client, T1).status_code == 201
    assert _checkin(client, T2).status_code == 201
    s = SessionFactory()
    try:
        newest = s.query(TimelineEvent).filter_by(
            occurred_at=T2, org_id=ORG
        ).first()
        assert newest is not None, "precondition: check-in timeline row exists"
        s.delete(newest)
        s.commit()
        # Recompute via the exact function the write paths call.
        service.recompute_contact_recency(s, contact_id=CONTACT_A, org_id=ORG)
        s.commit()
    finally:
        s.close()
    after = datetime.fromisoformat(_contact(client, CONTACT_A).json()[
        "last_interaction_at"])
    assert after == T1, "recency recomputed from remaining timeline rows"


# --------------------------------------------------------------------------
# C3 — monthly-active includes target, excludes control
# --------------------------------------------------------------------------
def test_c3_monthly_active_includes_target_excludes_control(client, db):
    _drive_all(client)
    resp = client.get("/metrics/monthly-active", params={
        "org_id": str(ORG), "site_id": str(SITE), "year": 2026, "month": 11,
    })
    assert resp.status_code == 200, resp.text
    ids = resp.json()["enterprise_ids"]
    assert str(TARGET) in ids, "target has 3 current-month interactions"
    assert str(CONTROL) not in ids, "control only has prior-month interaction"


def test_c3_prior_month_window_flips_membership(client, db):
    """Month-boundary guard: in October the control is in and target is out."""
    _drive_all(client)
    oct_ids = client.get("/metrics/monthly-active", params={
        "org_id": str(ORG), "site_id": str(SITE), "year": 2026, "month": 10,
    }).json()["enterprise_ids"]
    assert str(CONTROL) in oct_ids
    assert str(TARGET) not in oct_ids


def test_c3_month_boundary_inclusive_of_first_day(client, db):
    """Interaction exactly on the 1st of the month counts for that month."""
    first = datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert _visit(client, first).status_code == 201
    ids = client.get("/metrics/monthly-active", params={
        "org_id": str(ORG), "site_id": str(SITE), "year": 2026, "month": 11,
    }).json()["enterprise_ids"]
    assert str(TARGET) in ids


def test_c3_soft_deleted_interaction_not_counted(client, db):
    """A soft-deleted timeline row does not make an enterprise monthly-active."""
    from app.api import SessionFactory
    from app.models import TimelineEvent
    _drive_all(client, visit_at=datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc),
               checkin_at=datetime(2026, 11, 2, 9, 1, tzinfo=timezone.utc),
               sop_at=datetime(2026, 11, 2, 9, 2, tzinfo=timezone.utc))
    s = SessionFactory()
    try:
        s.query(TimelineEvent).filter(TimelineEvent.enterprise_id == TARGET).update(
            {TimelineEvent.deleted_at: datetime(2026, 11, 20, tzinfo=timezone.utc)},
            synchronize_session=False,
        )
        s.commit()
    finally:
        s.close()
    ids = client.get("/metrics/monthly-active", params={
        "org_id": str(ORG), "site_id": str(SITE), "year": 2026, "month": 11,
    }).json()["enterprise_ids"]
    # target's seeded rows are none (only the 3 just soft-deleted); control is Oct
    assert str(TARGET) not in ids
