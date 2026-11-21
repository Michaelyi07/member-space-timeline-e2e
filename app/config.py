"""Runtime configuration: all secrets/DSN come from environment variables only."""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    demo_org_id: uuid.UUID
    demo_site_id: uuid.UUID
    actor_id: uuid.UUID

    @classmethod
    def from_env(cls) -> "Settings":
        dsn = os.environ.get("DATABASE_URL")
        if not dsn:
            raise RuntimeError("DATABASE_URL must be provided via environment")
        return cls(
            database_url=dsn,
            demo_org_id=uuid.UUID(
                os.environ.get("DEMO_ORG_ID", "00000000-0000-0000-0000-000000000010")
            ),
            demo_site_id=uuid.UUID(
                os.environ.get("DEMO_SITE_ID", "00000000-0000-0000-0000-000000000011")
            ),
            actor_id=uuid.UUID(
                os.environ.get("DEMO_ACTOR_ID", "00000000-0000-0000-0000-000000000012")
            ),
        )
