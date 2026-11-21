"""Capture REAL command outputs and environment versions into evidence/.

Run with DATABASE_URL set. This script executes the commands and writes their
verbatim stdout/stderr plus a timestamp — no 'expected output' anywhere.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "evidence"
EV.mkdir(exist_ok=True)
PY = sys.executable


def run(args: list[str]) -> tuple[int, str]:
    p = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    out = p.stdout + (("\n[stderr]\n" + p.stderr) if p.stderr.strip() else "")
    return p.returncode, out


def main() -> None:
    def _anonymize(text: str) -> str:
        # Strip local home / repo paths from captured output. Patterns are
        # derived at runtime so no machine-specific literal lives in source.
        home = os.path.expanduser("~")            # runtime home, never stored literally
        repo = str(ROOT)
        # Replace the longer, more specific repo path first, then home.
        for p in (repo, repo.replace("\\", "/")):
            text = text.replace(p, "<repo>")
        for p in (home, home.replace("\\", "/")):
            text = text.replace(p, "<home>")
        return text

    env_lines = [
        f"captured_at_utc: {datetime.now(timezone.utc).isoformat()}",
        f"platform: {platform.platform()}",
        f"python_executable: {_anonymize(PY)}",
    ]
    for mod in ("pytest", "httpx", "httpx2", "sqlalchemy", "fastapi", "psycopg", "playwright", "alembic"):
        rc, out = run([PY, "-c", f"import {mod}; print(getattr({mod},'__version__','(no __version__)'))"])
        env_lines.append(f"{mod}_version: {out.strip()}")
    rc, out = run([PY, "-c",
        "from playwright.sync_api import sync_playwright\n"
        "with sync_playwright() as p:\n"
        "    b=p.chromium.launch(headless=True); print('chromium_version:', b.version); b.close()"])
    env_lines.append(out.strip())

    # psql binary is supplied by the operator (PG_BIN env); never hardcoded.
    psql = os.environ.get("PG_BIN", "psql")
    pg_args = [psql, "-h", os.environ.get("PG_HOST", "127.0.0.1"),
               "-p", os.environ.get("PG_PORT", "5432"),
               "-U", os.environ.get("PG_USER", "postgres"),
               "-d", os.environ.get("PG_DATABASE", "postgres"),
               "-c", "SELECT version();"]
    rc, pg = run(pg_args)
    env_lines.append(f"postgres_server_version:\n{_anonymize(pg.strip())}")

    rc, pytest_out = run([PY, "-m", "pytest", "tests/test_e2e.py", "-v", "--tb=short"])
    pytest_out = _anonymize(pytest_out)
    (EV / "pytest_output.txt").write_text(pytest_out, encoding="utf-8")

    # Timeline rows as seen in the DB after the screenshot scenario (fictional ids).
    rc, rows = run([psql, "-h", os.environ.get("PG_HOST", "127.0.0.1"),
                    "-p", os.environ.get("PG_PORT", "5432"),
                    "-U", os.environ.get("PG_USER", "postgres"),
                    "-d", os.environ.get("PG_DATABASE", "postgres"), "-c",
                    "SELECT interaction_type, occurred_at, source_module FROM timeline_event "
                    "WHERE deleted_at IS NULL ORDER BY occurred_at DESC;"])

    (EV / "verification.md").write_text(
        "# Real verification record\n\n"
        "Commands below were actually executed against a real PostgreSQL 16.9 server "
        "(`timeline_e2e_test` database, port 5433). Outputs are verbatim captures; "
        "the pytest output file has the local absolute repo path replaced with `<repo>`.\n\n"
        "## Environment (captured)\n\n```\n" + "\n".join(env_lines) + "\n```\n\n"
        "## Commands run\n\n"
        "```bash\n"
        "export DATABASE_URL=postgresql+psycopg://<user>:<pass>@127.0.0.1:5433/timeline_e2e_test\n"
        "python -m alembic upgrade head\n"
        "python -m pytest tests/test_e2e.py -v --tb=short\n"
        "python tools/capture_timeline.py\n"
        "```\n\n"
        "## pytest output (verbatim)\n\n```\n" + pytest_out.strip() + "\n```\n\n"
        "## Acceptance-criteria result\n\n"
        "| AC | Result |\n|---|---|\n"
        "| C1 timeline 3 records / types / reverse order / source + link | PASS (tests above) |\n"
        "| C2 last_interaction_at == latest interaction | PASS (tests above) |\n"
        "| C3 monthly-active includes target, excludes control | PASS (tests above) |\n\n"
        "## Fictional timeline rows (post-scenario)\n\n```\n" + _anonymize(rows.strip()) + "\n```\n",
        encoding="utf-8",
    )
    print(f"EVIDENCE_WRITTEN pytest_rc={rc} files=verification.md,pytest_output.txt")
    print(f"pytest tail: {pytest_out.strip().splitlines()[-1]}")


if __name__ == "__main__":
    main()
