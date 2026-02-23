# app/settings.py
from __future__ import annotations

import os


def _normalize_db_url(url: str | None) -> str | None:
    if not url:
        return None
    u = url.strip()

    # Render sometimes uses postgres://
    if u.startswith("postgres://"):
        u = u.replace("postgres://", "postgresql+psycopg2://", 1)

    # Some setups use postgresql://
    if u.startswith("postgresql://"):
        u = u.replace("postgresql://", "postgresql+psycopg2://", 1)

    return u


class Config:
    # ======================
    # Core
    # ======================
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

    # ======================
    # Database
    # ======================
    # Priority:
    # 1) DATABASE_URL (Render/production)
    # 2) SQLALCHEMY_DATABASE_URI (manual override)
    # 3) Local default
    _env_db = _normalize_db_url(os.environ.get("DATABASE_URL"))
    _override_db = _normalize_db_url(os.environ.get("SQLALCHEMY_DATABASE_URI"))

    SQLALCHEMY_DATABASE_URI = (
        _override_db
        or _env_db
        or "postgresql+psycopg2://thumbi:1010@localhost:5432/rizara"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ======================
    # Flask-Limiter
    # ======================
    RATELIMIT_STORAGE_URI = (
        os.environ.get("LIMITER_STORAGE_URL")
        or os.environ.get("REDIS_URL")
        or "memory://"
    )
    RATELIMIT_HEADERS_ENABLED = True

    # ======================
    # Proxy / Render / Gunicorn
    # ======================
    PREFERRED_URL_SCHEME = os.environ.get("PREFERRED_URL_SCHEME", "https")