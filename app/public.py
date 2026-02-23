# app/public.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets

from flask import Blueprint, abort, redirect, request, url_for

public = Blueprint("public", __name__)


# =========================================================
# Time helpers
# =========================================================
def utcnow_aware() -> datetime:
    """Timezone-aware UTC 'now'."""
    return datetime.now(timezone.utc)


def utcnow_naive() -> datetime:
    """
    Naive UTC 'now' for comparison with DB columns that are
    timestamp without time zone (common in SQLAlchemy/Postgres).
    """
    return utcnow_aware().replace(tzinfo=None)


def as_naive_utc(dt: datetime | None) -> datetime | None:
    """Normalize an aware datetime to naive UTC; leave naive as-is."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


# =========================================================
# Client metadata helpers
# =========================================================
def _client_ip() -> str:
    """
    Prefer X-Forwarded-For if present (when behind proxy/LB).
    Best practice: also configure ProxyFix in production.
    """
    xff = (request.headers.get("X-Forwarded-For") or "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return (request.remote_addr or "").strip() or "0.0.0.0"


def _normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def _safe_user_agent(maxlen: int = 255) -> str:
    ua = (request.headers.get("User-Agent") or "").strip()
    return (ua[:maxlen] if ua else "unknown")


# =========================================================
# Token helper (optional – admin uses its own generator too)
# =========================================================
def generate_buyer_sign_token(days_valid: int = 7) -> tuple[str, datetime]:
    """
    Generates an unguessable token plus a naive UTC expiry time.
    Matches typical DB columns: timestamp without time zone.
    """
    token = secrets.token_urlsafe(32)
    expires_at = utcnow_naive() + timedelta(days=days_valid)
    return token, expires_at


# =========================================================
# Public signing route (redirect-only)
# =========================================================
@public.route("/sign/<token>", methods=["GET", "POST"])
def sign_document(token: str):
    """
    Compatibility shim. The canonical signer lives on `main` in app/routes.py.

    - GET  -> main.sign_document_get
    - POST -> main.sign_document_post
    """
    token = (token or "").strip()
    if not token:
        abort(404)

    if request.method == "POST":
        return redirect(url_for("main.sign_document_post", token=token), code=307)

    return redirect(url_for("main.sign_document_get", token=token), code=302)