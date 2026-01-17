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

from app.models import User

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ======================
# Rate Limiter
# ======================
limiter = Limiter(
    key_func=get_remote_address,  # Limits per IP
    default_limits=[],            # No global limits by default
)
