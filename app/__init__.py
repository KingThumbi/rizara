# app/__init__.py
from __future__ import annotations

from flask import Flask, render_template, redirect, url_for, request
from flask_login import current_user

from .settings import Config
from .extensions import db, migrate, login_manager, limiter


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    # ======================
    # Initialize Extensions
    # ======================
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    limiter.init_app(app)

    # ======================
    # Import Models (CRITICAL)
    # ======================
    from . import models  # noqa: F401

    # ======================
    # Global template context (Company identity)
    # ======================
    from .config.company import company_context

    @app.context_processor
    def inject_company():
        # Gives templates:
        # - COMPANY_NAME, COMPANY_EMAIL, COMPANY_PHONE, etc.
        # - COMPANY_PROFILE (backward compatible dict)
        return company_context()

    # ======================
    # Register Blueprints
    # ======================
    from .routes import main
    from .auth import auth
    from .admin import admin_bp
    from .public import public  # public blueprint (signing flow)

    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(admin_bp)
    app.register_blueprint(public)

    # ======================
    # Global Terms Enforcement (External users only)
    # ======================
    from .utils.guards import requires_terms

    @app.before_request
    def enforce_terms_acceptance():
        if not getattr(current_user, "is_authenticated", False):
            return None

        if not requires_terms(current_user) or getattr(current_user, "accepted_terms", False):
            return None

        endpoint = request.endpoint or ""
        if endpoint.startswith("static"):
            return None

        allowed_endpoints = {
            "auth.accept_terms",
            "auth.logout",
            "auth.login",
        }
        if endpoint in allowed_endpoints:
            return None

        next_path = request.full_path or request.path or "/"
        return redirect(url_for("auth.accept_terms", next=next_path))

    # ======================
    # Rate limit error handler
    # ======================
    @app.errorhandler(429)
    def ratelimit_handler(e):
        return "Too many requests. Please try again later.", 429

    # ======================
    # Forbidden handler
    # ======================
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("403.html"), 403

    # ======================
    # Not found handler
    # ======================
    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404

    return app