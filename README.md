# Enterprise Timeline Closed Loop — E2E tests & evidence

Fictional test data only. No real person, enterprise, or client name appears in
this repository. This deliverable covers one ticket: three heterogeneous touchpoints
(workbench visit, API event check-in, completed SOP task) consolidated into one
reverse-chronological enterprise timeline, with exact per-contact recency and a
monthly-active metric that is window-correct.

## What is delivered

| Deliverable | File |
|---|---|
| E2E test cases (pytest + httpx) | `tests/test_e2e.py`, `tests/conftest.py` |
| Control-data seed script | `seed.py` |
| Timeline screenshot (Playwright) | `screenshots/timeline.png` |
| Screenshot generator | `tools/capture_timeline.py` |
| Schema / migration | `migrations/versions/0001_baseline.py`, `migrations/env.py`, `alembic.ini` |
| Real verification records | `evidence/verification.md`, `evidence/pytest_output.txt` |
| FastAPI app (system under test) | `app/` |

## Environment & versions (verified, not expected)

- OS: Windows, Python 3.13.14 (managed venv)
- PostgreSQL **16.9** (real server, not SQLite) — see `evidence/verification.md`
- pytest 9.1.1 · httpx 0.28.1 (+ httpx2 2.16.2 for TestClient) · SQLAlchemy 2.1.8
- FastAPI 0.163.1 · psycopg3 3.3.9 · Playwright Chromium 151.0.7922.34

## Run & test

```bash
# 1. Provide the DSN via environment variable (no secrets in code).
export DATABASE_URL="postgresql+psycopg://<user>:<pass>@127.0.0.1:5433/<db>"

# 2. Install the Playwright browser (needed only to regenerate the screenshot).
python -m playwright install chromium

# 3. Create schema via Alembic (preferred; verified to match the model).
alembic upgrade head

# 4. Seed the fictional precondition + control enterprise (optional; tests seed themselves).
python seed.py --emit-json

# 5. Run the E2E suite against real PostgreSQL.
python -m pytest tests/test_e2e.py -v

# 6. Regenerate the timeline screenshot.
python tools/capture_timeline.py
```

Tests create their own fixtures and truncate business tables between cases, so
they are repeatable. A local PostgreSQL 16.x must be listening at `DATABASE_URL`;
SQLite is never used.

## Acceptance-criteria mapping (what the reviewer checks)

| AC | Test(s) | Evidence |
|---|---|---|
| C1 timeline: 3 records, types `visit`/`event_checkin`/`sop_task`, reverse-chronological, each with source module + jump link | `test_c1_timeline_types_and_reverse_chronological`, `test_c1_every_record_has_source_module_and_jump_link`, `test_c1_ordering_is_time_based_not_insertion_based`, `test_c1_literal_enum_order_when_times_are_visit_newest` | pytest output + `screenshots/timeline.png` |
| C2 `last_interaction_at` equals most recent interaction | `test_c2_recency_updates_each_step_and_equals_latest`, `test_c2_recency_never_regresses_on_out_of_order_writes`, `test_c2_recency_is_sourced_from_timeline_rows`, `test_c1_multi_contact_rolls_up_without_overwriting_recency` | pytest output |
| C3 monthly-active includes target, excludes prior-month control | `test_c3_monthly_active_includes_target_excludes_control`, `test_c3_prior_month_window_flips_membership`, `test_c3_month_boundary_inclusive_of_first_day`, `test_c3_soft_deleted_interaction_not_counted` | pytest output |

Ordering is proven by a *pair* of tests: `test_c1_timeline_types_and_reverse_chronological`
inserts in time-ascending order and expects time-descending output, while
`test_c1_ordering_is_time_based_not_insertion_based` inserts in the opposite
order. Only together do they rule out an insert-order ("heap order") sort.
`test_c2_recency_never_regresses_on_out_of_order_writes` makes a later API call
carry an earlier timestamp; a naive "write the caller's parameter" implementation
would roll recency back and fail. `test_c2_recency_is_sourced_from_timeline_rows`
then deletes the newest timeline row and re-computes via the same service the
write paths call, confirming the value comes from persisted rows.

## Integration points (stubs → real modules)

This ticket depends on other tickets' interfaces. Per the ticket's convention,
those are stubbed here; swap the stubs for real clients without changing the
timeline contract.

| Dependency | Ticket | Stub location | Real integration point |
|---|---|---|---|
| CRM core objects (enterprise, contact, visit, event, check-in) | S2-CRM | `app/models.py` local tables; paths in `app/service.py` | Replace `record_visit` / `checkin_event` with S2-CRM REST calls; keep the `timeline_event` write + `recompute_contact_recency` in the same transaction. |
| SOP engine & workbench (dispatched to-do completion) | S3-SOP | `SopTask` table + `complete_sop_task` | Replace task lookup/completion with S3-SOP API; emit the same `sop_task` timeline row (`source_module=S3-SOP/workbench.tasks`). |
| Management dashboard (monthly-active metric) | S3-DASH | `monthly_active_enterprises` | Expose as a DASH read model; window is `[first of month, first of next month)` in UTC, live rows only (`deleted_at IS NULL`). |

All cross-tenant queries are scoped by `org_id` (and `site_id` where applicable);
there is no object-id-only lookup that could cross tenants.

## Data & confidentiality conventions

- All enterprises/contacts/events are fictional; no real personal or enterprise data.
- No client name anywhere (including code comments and screenshot).
- Secrets: `DATABASE_URL` read from env only; no hardcoded credentials. The demo
  org/site/actor ids are non-secret constants used purely to scope fictional rows.
- No third-party SDK that transmits data overseas.
- Monetary value (`ticket_price_cents`) is stored as integer cents.
- Business tables carry `id` (UUID), `org_id`, `site_id`, `created_at`,
  `created_by`, `updated_at`, `deleted_at` (soft delete).
