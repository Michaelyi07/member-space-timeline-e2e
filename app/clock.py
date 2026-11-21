"""Freezable clock for deterministic, reproducible interaction timestamps."""
from __future__ import annotations

from datetime import datetime, timezone

_FROZEN: datetime | None = None


def utcnow() -> datetime:
    """Return the frozen time if set, otherwise real UTC now."""
    if _FROZEN is not None:
        return _FROZEN
    return datetime.now(timezone.utc)


def freeze(moment: datetime) -> None:
    global _FROZEN
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    _FROZEN = moment


def unfreeze() -> None:
    global _FROZEN
    _FROZEN = None


def is_frozen() -> bool:
    return _FROZEN is not None
