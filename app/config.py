import os


class Config:
    # ======================
    # Core
    # ======================
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

    # ======================
    # Database
    # ======================
    # Render provides DATABASE_URL like:
    # postgres://user:pass@host:port/db
    # SQLAlchemy prefers postgresql+psycopg2://
    _db_url = os.environ.get("DATABASE_URL")

    if _db_url and _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql+psycopg2://", 1)

    SQLALCHEMY_DATABASE_URI = (
        _db_url
        or "postgresql+psycopg2://thumbi:1010@localhost:5432/rizara"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ======================
    # Flask-Limiter
    # ======================
    # Use Redis on Render, fallback to memory locally
    RATELIMIT_STORAGE_URI = (
        os.environ.get("LIMITER_STORAGE_URL")
        or os.environ.get("REDIS_URL")
        or "memory://"
    )

    RATELIMIT_HEADERS_ENABLED = True

    # ======================
    # Proxy / Render / Gunicorn
    # ======================
    # Ensures correct client IP when behind Render / proxy
    PREFERRED_URL_SCHEME = "https"
