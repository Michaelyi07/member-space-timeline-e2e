"""Generate the enterprise-timeline screenshot with Playwright.

Drives the three interactions against the API on real PostgreSQL, renders a
minimal standalone timeline page from the resulting data, and screenshots it.
All content is fictional. Run with DATABASE_URL set.
"""
from __future__ import annotations

import html
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import api, clock
from app.models import Base
from seed import ORG, SITE, ACTOR, seed_all

# ids (kept local & explicit so the script is self-contained)
TARGET = uuid.UUID("00000000-0000-0000-0000-000000000001")
CONTACT_A = uuid.UUID("00000000-0000-0000-0000-000000000101")
EVENT = uuid.UUID("00000000-0000-0000-0000-000000000201")
SOP = uuid.UUID("00000000-0000-0000-0000-000000000301")
TABLES = ["timeline_event", "event_checkin", "visit", "sop_task",
          "member_event", "contact", "enterprise"]


def main() -> None:
    url = os.environ["DATABASE_URL"]
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE " + ", ".join(TABLES) + " RESTART IDENTITY CASCADE"))
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    clock.freeze(datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc))
    seed_all(db, now=datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc))
    db.commit()
    db.close()

    api.bind_engine(engine)
    client = TestClient(api.app, base_url="http://testserver")
    H = {"org_id": str(ORG), "site_id": str(SITE), "actor_id": str(ACTOR)}
    client.post("/interactions/visit", json={**H,
        "enterprise_id": str(TARGET), "contact_id": str(CONTACT_A),
        "visit_type": "in_person", "occurred_at": "2026-11-15T09:05:00+00:00",
        "summary": "Fictional onboarding visit", "next_steps": "Fictional intro to partner"})
    client.post("/interactions/event-checkin", json={**H,
        "enterprise_id": str(TARGET), "contact_id": str(CONTACT_A),
        "event_id": str(EVENT), "occurred_at": "2026-11-15T09:10:00+00:00"})
    client.post("/interactions/sop-complete", json={**H,
        "task_id": str(SOP), "occurred_at": "2026-11-15T09:15:00+00:00"})

    recs = client.get(f"/enterprises/{TARGET}/timeline", params={
        "org_id": str(ORG), "site_id": str(SITE)}).json()["records"]

    type_label = {"visit": "Visit", "event_checkin": "Event check-in", "sop_task": "SOP task"}

    def _utc_iso(value: str) -> str:
        # Normalize the DB session's local-offset timestamp to explicit UTC so
        # the "UTC" column header matches the rendered value.
        return datetime.fromisoformat(value).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    rows = "\n".join(
        f"<tr><td class='t'>{html.escape(_utc_iso(r['occurred_at']))}</td>"
        f"<td><span class='badge {r['interaction_type']}'>{type_label[r['interaction_type']]}</span></td>"
        f"<td>{html.escape(r['source_module'])}</td>"
        f"<td><a href='{html.escape(r['jump_link'])}'>{html.escape(r['jump_link'])}</a></td></tr>"
        for r in recs
    )
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<style>
body{{font-family:Segoe UI,Arial,sans-serif;background:#f7f8fa;color:#1f2329;margin:32px}}
h1{{font-size:22px}} .sub{{color:#646a73;margin-bottom:20px}}
table{{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 4px #0001}}
th,td{{border:1px solid #e5e6eb;padding:10px 12px;text-align:left;font-size:13px}}
th{{background:#f2f3f5}} a{{color:#0052d9;text-decoration:none}}
.t{{white-space:nowrap}}
.badge{{padding:2px 8px;border-radius:10px;font-size:12px;color:#fff}}
.visit{{background:#0052d9}}.event_checkin{{background:#00a870}}.sop_task{{background:#ed7b2f}}
</style></head><body>
<h1>Enterprise Timeline — Fictional Target Enterprise</h1>
<div class="sub">3 interactions · reverse chronological · source module + jump link · fictional test data</div>
<table><thead><tr><th>Interaction time (UTC)</th><th>Type</th><th>Source module</th><th>Jump link</th></tr></thead>
<tbody>{rows}</tbody></table></body></html>"""

    out = Path(__file__).resolve().parents[1] / "screenshots" / "timeline.png"
    out.parent.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page_obj = browser.new_page(viewport={"width": 1280, "height": 520}, device_scale_factor=2)
        page_obj.set_content(page)
        page_obj.screenshot(path=str(out), full_page=True)
        browser.close()
    print(f"SCREENSHOT {out} bytes={out.stat().st_size} records={len(recs)}")
    print("ORDER", [r["interaction_type"] for r in recs])
    engine.dispose()


if __name__ == "__main__":
    main()
