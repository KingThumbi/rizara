import os

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# ======================
# Database
# ======================
db = SQLAlchemy()
migrate = Migrate()

# ======================
# Login Manager
# ======================
login_manager = LoginManager()
login_manager.login_view = "auth.login"

from app.models import User  # keep as-is if it works in your app

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ======================
# Rate Limiter
# ======================
# Prefer Redis in production (Render), fall back to in-memory locally.
# Set LIMITER_STORAGE_URL / REDIS_URL on Render to enable Redis storage.
_limiter_storage = (
    os.getenv("LIMITER_STORAGE_URL")
    or os.getenv("REDIS_URL")
    or "memory://"
)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],              # No global limits by default
    storage_uri=_limiter_storage,   # <- fixes the warning in production
)
