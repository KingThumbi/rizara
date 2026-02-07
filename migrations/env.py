# migrations/env.py
from __future__ import annotations

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

# Setup Python logging from the config file (if present and valid)
if config.config_file_name:
    try:
        fileConfig(config.config_file_name, disable_existing_loggers=False)
    except KeyError:
        # Some alembic.ini files don't define logging sections; proceed without it.
        pass

logger = logging.getLogger("alembic.env")

# -----------------------------------------------------------------------------
# URL + metadata resolution strategy (Render-safe)
#
# - If DATABASE_URL (or RENDER_DB_URL) is set: run without Flask app context.
# - Otherwise: assume local Flask-Migrate workflow and use current_app engine/db.
# -----------------------------------------------------------------------------
DB_URL = os.getenv("DATABASE_URL") or os.getenv("RENDER_DB_URL")

USING_FLASK_MIGRATE = False
target_db = None
current_app = None  # only set in Flask-Migrate path


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
    from app.extensions import db  # runtime import is intentional

    if hasattr(db, "metadatas") and getattr(db, "metadatas"):
        return db.metadatas.get(None) or db.metadata
    return db.metadata


def _bootstrap_flask_migrate():
    """Initialize Flask-Migrate context helpers (engine/url/metadata) when no DB_URL is set."""
    global USING_FLASK_MIGRATE, target_db, current_app  # noqa: PLW0603

    try:
        from flask import current_app as flask_current_app  # runtime import
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "DATABASE_URL (or RENDER_DB_URL) is not set, and Flask is not available. "
            "Set DATABASE_URL for non-Flask environments."
        ) from exc

    current_app = flask_current_app
    USING_FLASK_MIGRATE = True
    target_db = current_app.extensions["migrate"].db

    def get_engine():
        try:
            # Flask-SQLAlchemy<3 and Alchemical
            return current_app.extensions["migrate"].db.get_engine()
        except (TypeError, AttributeError, KeyError):
            # Flask-SQLAlchemy>=3
            return current_app.extensions["migrate"].db.engine

    def get_engine_url():
        try:
            return get_engine().url.render_as_string(hide_password=False).replace("%", "%%")
        except AttributeError:
            return str(get_engine().url).replace("%", "%%")

    return get_engine, get_engine_url


# -----------------------------------------------------------------------------
# Legacy tables that may exist in the database but are not managed by Rizara.
# We explicitly IGNORE them so Alembic never autogenerates DROP/ALTER for them.
# -----------------------------------------------------------------------------
LEGACY_TABLES = {"customers", "subscriptions", "packages", "transactions"}


def include_object(object_, name, type_, reflected, compare_to):
    # Ignore legacy tables entirely.
    if type_ == "table" and name in LEGACY_TABLES:
        return False
    return True


# -----------------------------------------------------------------------------
# Configure sqlalchemy.url
# -----------------------------------------------------------------------------
if DB_URL:
    _set_sqlalchemy_url(DB_URL)
    get_engine = None
else:
    get_engine, get_engine_url = _bootstrap_flask_migrate()
    _set_sqlalchemy_url(get_engine_url())


def get_metadata():
    """
    Return SQLAlchemy MetaData for autogenerate.

    - Non-Flask (Render/CI): import db.metadata directly.
    - Flask-Migrate: use migrate extension db metadata.
    """
    if not USING_FLASK_MIGRATE:
        return _import_app_db_metadata()

    if hasattr(target_db, "metadatas"):
        return target_db.metadatas[None]
    return target_db.metadata


# -----------------------------------------------------------------------------
# Prevent empty autogenerate migrations (keeps history clean)
# -----------------------------------------------------------------------------
def process_revision_directives(ctx, revision, directives):
    cmd_opts = getattr(config, "cmd_opts", None)
    if cmd_opts and getattr(cmd_opts, "autogenerate", False):
        script = directives[0]
        if script.upgrade_ops.is_empty():
            directives[:] = []
            logger.info("No changes in schema detected.")


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
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
        process_revision_directives=process_revision_directives,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    if USING_FLASK_MIGRATE:
        # Use Flask-Migrate provided configure_args (if present)
        conf_args = current_app.extensions["migrate"].configure_args or {}
        conf_args.setdefault("process_revision_directives", process_revision_directives)
        conf_args.setdefault("include_object", include_object)
        conf_args.setdefault("compare_type", True)
        conf_args.setdefault("compare_server_default", True)

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

    # Non-Flask path (Render/CI): create engine from sqlalchemy.url
    from sqlalchemy import create_engine  # runtime import is intentional

    url = config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("No sqlalchemy.url configured. Set DATABASE_URL / RENDER_DB_URL.")

    engine = create_engine(url)

    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            include_object=include_object,
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
