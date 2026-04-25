from __future__ import annotations

import uuid
from datetime import date
from typing import Any


def parse_float(val: Any) -> float | None:
    try:
        if val is None or str(val).strip() == "":
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


def parse_int(val: Any) -> int | None:
    try:
        if val is None or str(val).strip() == "":
            return None
        return int(val)
    except (TypeError, ValueError):
        return None


def parse_date(val: Any) -> date | None:
    try:
        if not val:
            return None
        return date.fromisoformat(str(val))
    except (TypeError, ValueError):
        return None


def parse_uuid(val: Any) -> uuid.UUID | None:
    try:
        if val is None:
            return None
        s = str(val).strip()
        if not s:
            return None
        return uuid.UUID(s)
    except Exception:
        return None


def safe_enum_value(value: Any) -> Any:
    try:
        return value.value
    except Exception:
        return value