# app/public.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets

from flask import Blueprint, abort, render_template, request

from .extensions import db
from .models import Document


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
    return (request.remote_addr or "").strip()


def _normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def _safe_user_agent(maxlen: int = 255) -> str:
    ua = (request.headers.get("User-Agent") or "").strip()
    return ua[:maxlen]


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
# Public signing route
# =========================================================
@public.route("/sign/<token>", methods=["GET", "POST"])
def sign_document(token: str):
    token = (token or "").strip()
    if not token:
        abort(404)

    doc = Document.query.filter(Document.buyer_sign_token == token).first()
    if not doc:
        # Do not reveal whether token existed or not
        return render_template("public/sign_invalid.html", reason="invalid"), 404

    # Block signing in terminal states
    if doc.status in ("buyer_signed", "executed", "void"):
        # 410 Gone is appropriate for "used/finished" links
        return render_template("public/sign_invalid.html", reason="already_signed"), 410

    # Must have expiry for a valid signing session
    expires_at = as_naive_utc(doc.buyer_sign_token_expires_at)
    if not expires_at:
        return render_template("public/sign_invalid.html", reason="invalid"), 400

    # Expiry check (naive UTC)
    now = utcnow_naive()
    if expires_at <= now:
        if doc.status not in ("expired", "void", "executed", "buyer_signed"):
            doc.status = "expired"
            db.session.commit()
        return render_template("public/sign_invalid.html", reason="expired"), 410

    # -----------------------------
    # GET: show signing page
    # -----------------------------
    if request.method == "GET":
        return render_template("public/sign_document.html", document=doc, token=token)

    # -----------------------------
    # POST: validate + persist signature
    # -----------------------------
    full_name = (request.form.get("full_name") or "").strip()
    email = _normalize_email(request.form.get("email"))
    accept = request.form.get("accept")

    errors: list[str] = []
    if len(full_name) < 2:
        errors.append("Please enter your full name.")
    if "@" not in email or "." not in email:
        errors.append("Please enter a valid email address.")
    if not accept:
        errors.append("You must accept the terms to sign.")

    if errors:
        return (
            render_template(
                "public/sign_document.html",
                document=doc,
                token=token,
                errors=errors,
                full_name=full_name,
                email=email,
            ),
            400,
        )

    # Persist signature (store timestamps consistently)
    doc.buyer_signed_at = utcnow_aware()
    doc.buyer_sign_name = full_name
    doc.buyer_sign_email = email
    doc.buyer_sign_ip = _client_ip()
    doc.buyer_sign_user_agent = _safe_user_agent(255)
    doc.status = "buyer_signed"

    # Invalidate token to prevent reuse
    doc.buyer_sign_token = None
    doc.buyer_sign_token_expires_at = None

    db.session.commit()

    return render_template("public/sign_success.html", document=doc)
