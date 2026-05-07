from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from flask import Blueprint, Flask
from flask_login import LoginManager, UserMixin, login_user
from werkzeug.security import generate_password_hash

import app.auth as auth_module
from app.extensions import limiter
from app.utils.auth_security import (
    lockout_is_active,
    register_failed_login,
    reset_login_security,
)
from app.utils.guards import operation_required


class DummySession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class DummyQuery:
    def __init__(self, user=None):
        self.user = user

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.user


class DummyUser(UserMixin):
    def __init__(self, role="staff"):
        self.id = "1"
        self.name = "Test User"
        self.email = "user@example.com"
        self.role = role
        self.password_hash = generate_password_hash("CorrectPass123!")
        self.failed_login_attempts = 0
        self.locked_until = None
        self.last_login_at = None


def test_failed_login_increment_and_lockout_threshold(app):
    user = DummyUser()
    app.config.update(LOGIN_MAX_FAILED_ATTEMPTS=2, LOGIN_LOCKOUT_MINUTES=15)

    with app.test_request_context("/login", method="POST"):
        locked = register_failed_login(user, now_utc=datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert locked is False
        assert user.failed_login_attempts == 1
        assert user.locked_until is None

        locked = register_failed_login(user, now_utc=datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert locked is True
        assert user.failed_login_attempts == 2
        assert user.locked_until == datetime(2026, 1, 1, 0, 15)


def test_lockout_enforcement_helper(app):
    user = DummyUser()
    user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=5)

    with app.test_request_context("/login", method="POST"):
        assert lockout_is_active(user) is True


def test_successful_login_reset_behavior():
    user = DummyUser()
    user.failed_login_attempts = 3
    user.locked_until = datetime(2026, 1, 1, 0, 15)

    reset_login_security(user)

    assert user.failed_login_attempts == 0
    assert user.locked_until is None


def make_auth_app(monkeypatch, user=None, rate_limit="2 per minute"):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="test-secret",
        TESTING=True,
        LOGIN_RATE_LIMIT=rate_limit,
        LOGIN_MAX_FAILED_ATTEMPTS=5,
        LOGIN_LOCKOUT_MINUTES=10,
        RATELIMIT_ENABLED=True,
    )

    dashboard = Blueprint("main", __name__)

    @dashboard.get("/dashboard")
    def dashboard_view():
        return "dashboard"

    app.register_blueprint(dashboard)
    limiter.init_app(app)

    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return user if user and str(user.id) == str(user_id) else None

    query_user = SimpleNamespace(query=DummyQuery(user), email="email")
    monkeypatch.setattr(auth_module, "User", query_user)
    monkeypatch.setattr(auth_module, "render_template", lambda *_args, **_kwargs: "login")
    monkeypatch.setattr(auth_module.db, "session", DummySession())

    app.register_blueprint(auth_module.auth)
    return app


def test_locked_user_cannot_login(monkeypatch):
    user = DummyUser()
    user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=10)
    app = make_auth_app(monkeypatch, user=user, rate_limit="20 per minute")

    response = app.test_client().post(
        "/login",
        data={"email": user.email, "password": "CorrectPass123!"},
    )

    assert response.status_code == 423


def test_login_rate_limit_returns_429(monkeypatch):
    app = make_auth_app(monkeypatch, user=None, rate_limit="2 per minute")
    client = app.test_client()

    for _ in range(2):
        response = client.post("/login", data={"email": "missing@example.com", "password": "bad"})
        assert response.status_code == 200

    response = client.post("/login", data={"email": "missing@example.com", "password": "bad"})
    assert response.status_code == 429


def test_operation_required_denies_non_internal_role():
    app = Flask(__name__)
    app.config.update(SECRET_KEY="test-secret", TESTING=True)
    login_manager = LoginManager()
    login_manager.init_app(app)
    users = {
        "buyer": DummyUser(role="buyer"),
        "staff": DummyUser(role="staff"),
    }
    users["buyer"].id = "buyer"
    users["staff"].id = "staff"

    @login_manager.user_loader
    def load_user(user_id):
        return users.get(user_id)

    @app.post("/mutate")
    @operation_required("payments:record")
    def mutate():
        return "ok"

    client = app.test_client()

    with client.session_transaction() as session:
        session["_user_id"] = "buyer"
        session["_fresh"] = True
    assert client.post("/mutate").status_code == 403

    with client.session_transaction() as session:
        session["_user_id"] = "staff"
        session["_fresh"] = True
    response = client.post("/mutate")
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "ok"
