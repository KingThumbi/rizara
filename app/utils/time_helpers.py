from __future__ import annotations

from datetime import datetime, timezone


def utcnow_naive() -> datetime:
    return datetime.utcnow()


def utcnow_aware() -> datetime:
    return datetime.now(timezone.utc)


def is_expired(exp, now_utc_aware: datetime, now_utc_naive: datetime) -> bool:
    if not exp:
        return True
    try:
        if getattr(exp, "tzinfo", None) is None:
            return now_utc_naive > exp
        return now_utc_aware > exp
    except Exception:
        return True