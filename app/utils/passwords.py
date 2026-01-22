# app/utils/passwords.py
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Tuple

from werkzeug.security import check_password_hash, generate_password_hash


# =========================
# Password hashing / verify
# =========================
def hash_password(plain_password: str) -> str:
    """
    Hash a plaintext password using a strong KDF.
    Werkzeug's scrypt is memory-hard and suitable for production.
    """
    if not isinstance(plain_password, str) or not plain_password.strip():
        raise ValueError("Password must be a non-empty string.")
    return generate_password_hash(plain_password, method="scrypt")


def verify_password(password_hash: str, plain_password: str) -> bool:
    """Verify plaintext password against stored hash."""
    if not password_hash or not plain_password:
        return False
    return check_password_hash(password_hash, plain_password)


# =========================
# Password policy
# =========================
_PASSWORD_RULES = [
    (lambda s: len(s) >= 10, "Password must be at least 10 characters."),
    (lambda s: re.search(r"[A-Z]", s) is not None, "Include at least one uppercase letter."),
    (lambda s: re.search(r"[a-z]", s) is not None, "Include at least one lowercase letter."),
    (lambda s: re.search(r"\d", s) is not None, "Include at least one number."),
    (lambda s: re.search(r"[^\w\s]", s) is not None, "Include at least one symbol (e.g. !@#$)."),
]


def validate_password(plain_password: str) -> Tuple[bool, str]:
    """
    Returns (ok, message). If ok is False, message explains what to fix.
    """
    if not isinstance(plain_password, str):
        return False, "Password must be text."
    pw = plain_password.strip()
    if not pw:
        return False, "Password cannot be empty."

    for rule, msg in _PASSWORD_RULES:
        if not rule(pw):
            return False, msg
    return True, ""


# =========================
# Optional: login lockout
# =========================
def is_locked_out(locked_until) -> bool:
    """
    locked_until can be None or a datetime. Returns True if lock is active.
    """
    if not locked_until:
        return False
    now = datetime.now(timezone.utc)
    # If locked_until is naive, treat as UTC
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    return locked_until > now


def set_lockout(now_utc: datetime | None = None, minutes: int = 10):
    now = now_utc or datetime.now(timezone.utc)
    return now + timedelta(minutes=minutes)
