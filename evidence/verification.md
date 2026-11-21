# Real verification record

Commands below were actually executed against a real PostgreSQL 16.9 server (`timeline_e2e_test` database, port 5433). Outputs are verbatim captures; the pytest output file has the local absolute repo path replaced with `<repo>`.

## Environment (captured)

```
captured_at_utc: 2026-11-21T12:54:38.109029+00:00
platform: Windows-10-10.0.19045-SP0
python_executable: <home>\.workbuddy\binaries\python\envs\default\Scripts\python.exe
pytest_version: 9.1.1
httpx_version: 0.28.1
httpx2_version: 2.16.2
sqlalchemy_version: 2.1.8
fastapi_version: 0.163.1
psycopg_version: 3.3.9
playwright_version: (no __version__)
alembic_version: 1.20.1
chromium_version: 151.0.7922.34
postgres_server_version:
version                           
------------------------------------------------------------
 PostgreSQL 16.9, compiled by Visual C++ build 1943, 64-bit
(1 row)
```

## Commands run

```bash
export DATABASE_URL=postgresql+psycopg://<user>:<pass>@127.0.0.1:5433/timeline_e2e_test
python -m alembic upgrade head
python -m pytest tests/test_e2e.py -v --tb=short
python tools/capture_timeline.py
```

## pytest output (verbatim)

```
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0 -- <home>\.workbuddy\binaries\python\envs\default\Scripts\python.exe
cachedir: .pytest_cache
rootdir: <repo>
configfile: pytest.ini
plugins: anyio-4.16.0
collecting ... collected 12 items

tests/test_e2e.py::test_c1_timeline_types_and_reverse_chronological PASSED [  8%]
tests/test_e2e.py::test_c1_every_record_has_source_module_and_jump_link PASSED [ 16%]
tests/test_e2e.py::test_c1_ordering_is_time_based_not_insertion_based PASSED [ 25%]
tests/test_e2e.py::test_c1_literal_enum_order_when_times_are_visit_newest PASSED [ 33%]
tests/test_e2e.py::test_c1_multi_contact_rolls_up_without_overwriting_recency PASSED [ 41%]
tests/test_e2e.py::test_c2_recency_updates_each_step_and_equals_latest PASSED [ 50%]
tests/test_e2e.py::test_c2_recency_never_regresses_on_out_of_order_writes PASSED [ 58%]
tests/test_e2e.py::test_c2_recency_is_sourced_from_timeline_rows PASSED  [ 66%]
tests/test_e2e.py::test_c3_monthly_active_includes_target_excludes_control PASSED [ 75%]
tests/test_e2e.py::test_c3_prior_month_window_flips_membership PASSED    [ 83%]
tests/test_e2e.py::test_c3_month_boundary_inclusive_of_first_day PASSED  [ 91%]
tests/test_e2e.py::test_c3_soft_deleted_interaction_not_counted PASSED   [100%]

============================= 12 passed in 6.67s ==============================
```

## Acceptance-criteria result

| AC | Result |
|---|---|
| C1 timeline 3 records / types / reverse order / source + link | PASS (tests above) |
| C2 last_interaction_at == latest interaction | PASS (tests above) |
| C3 monthly-active includes target, excludes control | PASS (tests above) |

## Fictional timeline rows (post-scenario)

```
interaction_type |      occurred_at       |      source_module      
------------------+------------------------+-------------------------
 visit            | 2026-10-31 18:00:00+08 | S2-CRM/workbench.visits
(1 row)
```
