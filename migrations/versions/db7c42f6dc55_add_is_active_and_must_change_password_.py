"""Add is_active and must_change_password to user

Revision ID: db7c42f6dc55
Revises: 6b8791e879de
Create Date: 2026-01-22 22:48:00.486148

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'db7c42f6dc55'
down_revision = '6b8791e879de'
branch_labels = None
depends_on = None


def _has_col(table: str, col: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return any(c["name"] == col for c in insp.get_columns(table))


def upgrade():
    # Add columns only if missing (baseline may already include them)
    if not _has_col("user", "is_active"):
        op.add_column("user", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    if not _has_col("user", "must_change_password"):
        op.add_column("user", sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()))
    if not _has_col("user", "password_changed_at"):
        op.add_column("user", sa.Column("password_changed_at", sa.DateTime(), nullable=True))

    # Drop server defaults after backfill (clean schema) — only if columns exist
    if _has_col("user", "is_active"):
        op.alter_column("user", "is_active", server_default=None)
    if _has_col("user", "must_change_password"):
        op.alter_column("user", "must_change_password", server_default=None)


def downgrade():
    # Only drop if exists (keeps downgrade safe)
    if _has_col("user", "password_changed_at"):
        op.drop_column("user", "password_changed_at")
    if _has_col("user", "must_change_password"):
        op.drop_column("user", "must_change_password")
    if _has_col("user", "is_active"):
        op.drop_column("user", "is_active")