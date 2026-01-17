# app/__init__.py
from flask import Flask
from .extensions import db, migrate, login_manager, limiter
from .config import Config

def create_app():
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
    from . import models

    # ======================
    # Register Blueprints
    # ======================
    from .routes import main
    from .auth import auth

    app.register_blueprint(main)
    app.register_blueprint(auth)

    # ======================
    # Rate limit error handler
    # ======================
    @app.errorhandler(429)
    def ratelimit_handler(e):
        return "Too many requests. Please try again later.", 429

    return app
