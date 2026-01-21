import os
import sys
import logging
from logging.config import fileConfig

from alembic import context

# -----------------------------------------------------------------------------
# Ensure project root is on sys.path so "import app" works everywhere
# This file lives at: <project_root>/migrations/env.py
# -----------------------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Alembic Config object (reads whichever .ini you invoked Alembic with)
config = context.config

# Setup Python logging from the config file
if config.config_file_name:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# -----------------------------------------------------------------------------
# URL + metadata resolution strategy (Render-safe)
#
# 1) If DATABASE_URL is set (Render), use it and import db.metadata directly.
# 2) Otherwise (local Flask-Migrate workflow), use current_app + Flask-Migrate.
# -----------------------------------------------------------------------------
DB_URL = os.getenv("DATABASE_URL") or os.getenv("RENDER_DB_URL")

USING_FLASK_MIGRATE = False
target_db = None


def _set_sqlalchemy_url(url: str) -> None:
    """Set sqlalchemy.url in alembic config, escaping % for ConfigParser."""
    if not url:
        return
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))


def _import_app_db_metadata():
    """
    Import db.metadata without requiring a Flask app context.
    Adjust this import ONLY if your db object is defined elsewhere.
    """
    from app.extensions import db  # noqa: WPS433 (runtime import is intentional)

    # Flask-SQLAlchemy can expose metadatas in some setups
    if hasattr(db, "metadatas") and db.metadatas:
        return db.metadatas.get(None) or db.metadata
    return db.metadata


if DB_URL:
    # Render / CI / non-Flask context
    _set_sqlalchemy_url(DB_URL)
else:
    # Local Flask-Migrate context (requires app context)
    try:
        from flask import current_app  # noqa: WPS433
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "DATABASE_URL (or RENDER_DB_URL) is not set, and Flask is not available. "
            "Set DATABASE_URL for non-Flask environments."
        ) from exc

    def get_engine():
        try:
            # Flask-SQLAlchemy<3 and Alchemical
            return current_app.extensions["migrate"].db.get_engine()
        except (TypeError, AttributeError, KeyError):
            # Flask-SQLAlchemy>=3
            return current_app.extensions["migrate"].db.engine

    def get_engine_url():
        try:
            return (
                get_engine()
                .url.render_as_string(hide_password=False)
                .replace("%", "%%")
            )
        except AttributeError:
            return str(get_engine().url).replace("%", "%%")

    USING_FLASK_MIGRATE = True
    _set_sqlalchemy_url(get_engine_url())
    target_db = current_app.extensions["migrate"].db


def get_metadata():
    """
    Return SQLAlchemy MetaData for autogenerate.

    - Render/non-Flask: import db.metadata directly.
    - Flask-Migrate: use migrate extension db metadata.
    """
    if not USING_FLASK_MIGRATE:
        return _import_app_db_metadata()

    if hasattr(target_db, "metadatas"):
        return target_db.metadatas[None]
    return target_db.metadata


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError(
            "No sqlalchemy.url configured. Ensure DATABASE_URL is set or "
            "your Flask app context is available."
        )

    context.configure(
        url=url,
        target_metadata=get_metadata(),
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    # Prevent empty autogenerate migrations (keeps your history clean)
    def process_revision_directives(ctx, revision, directives):
        cmd_opts = getattr(config, "cmd_opts", None)
        if cmd_opts and getattr(cmd_opts, "autogenerate", False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info("No changes in schema detected.")

    if USING_FLASK_MIGRATE:
        # Use Flask-Migrate provided configure_args (if present)
        conf_args = current_app.extensions["migrate"].configure_args
        if conf_args.get("process_revision_directives") is None:
            conf_args["process_revision_directives"] = process_revision_directives

        connectable = get_engine()

        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=get_metadata(),
                **conf_args,
            )

            with context.begin_transaction():
                context.run_migrations()
        return

    # Non-Flask path (Render): create engine from DATABASE_URL
    from sqlalchemy import create_engine  # noqa: WPS433

    url = config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("No sqlalchemy.url configured. Set DATABASE_URL on Render.")

    engine = create_engine(url)

    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            process_revision_directives=process_revision_directives,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
