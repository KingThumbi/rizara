from flask import Flask, render_template
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
    from . import models  # noqa: F401

    # ======================
    # Register Blueprints
    # ======================
    from .routes import main
    from .auth import auth
    from .admin import admin_bp

    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(admin_bp)

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

    return app
