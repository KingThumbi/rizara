from __future__ import annotations

from datetime import datetime

from flask import current_app, request

from app.utils.passwords import is_locked_out, set_lockout


def client_ip() -> str:
    forwarded_for = (request.headers.get("X-Forwarded-For") or "").strip()
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return (request.remote_addr or "").strip() or "unknown"


def audit_auth_event(event_type: str, *, email: str, user=None, reason: str | None = None) -> None:
    logger = getattr(current_app, "logger", None)
    if not logger:
        return

    logger.warning(
        "auth_event=%s email=%s user_id=%s reason=%s ip=%s user_agent=%s",
        event_type,
        email or "-",
        getattr(user, "id", None) if user else None,
        reason or "-",
        client_ip(),
        (request.headers.get("User-Agent") or "-")[:255],
    )


def lockout_is_active(user) -> bool:
    return bool(user and is_locked_out(getattr(user, "locked_until", None)))


def register_failed_login(user, *, now_utc: datetime | None = None) -> bool:
    attempts = int(getattr(user, "failed_login_attempts", 0) or 0) + 1
    user.failed_login_attempts = attempts

    threshold = int(current_app.config.get("LOGIN_MAX_FAILED_ATTEMPTS", 5))
    if attempts >= threshold:
        minutes = int(current_app.config.get("LOGIN_LOCKOUT_MINUTES", 10))
        locked_until = set_lockout(now_utc=now_utc, minutes=minutes)
        user.locked_until = locked_until.replace(tzinfo=None)
        return True

    return False


def reset_login_security(user) -> None:
    user.failed_login_attempts = 0
    user.locked_until = None
