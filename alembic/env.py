from logging.config import fileConfig
from sqlalchemy import pool
from alembic import context

# =========================================================
# Alembic Config
# =========================================================
config = context.config

# Set up logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# =========================================================
# Import Flask app and models
# =========================================================
from app import create_app
from app.extensions import db
from app.models import *

# Use the Flask SQLAlchemy metadata for autogenerate
target_metadata = db.metadata

# =========================================================
# Offline migrations
# =========================================================
def run_migrations_offline():
    url = db.engine.url  # db.engine is fine here
    context.configure(
        url=str(url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

# =========================================================
# Online migrations
# =========================================================
def run_migrations_online():
    app = create_app()
    # Push application context
    with app.app_context():
        connectable = db.engine

        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata
            )

            with context.begin_transaction():
                context.run_migrations()

# =========================================================
# Entry point
# =========================================================
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
