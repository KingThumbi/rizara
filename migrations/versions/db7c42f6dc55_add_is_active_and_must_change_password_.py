"""Add is_active and must_change_password to user

Revision ID: db7c42f6dc55
Revises: 6b8791e879de
Create Date: 2026-01-22 22:48:00.486148

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'db7c42f6dc55'
down_revision = '6b8791e879de'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("user", sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("user", sa.Column("password_changed_at", sa.DateTime(), nullable=True))

    # Drop server defaults after backfill (clean schema)
    op.alter_column("user", "is_active", server_default=None)
    op.alter_column("user", "must_change_password", server_default=None)


def downgrade():
    op.drop_column("user", "password_changed_at")
    op.drop_column("user", "must_change_password")
    op.drop_column("user", "is_active")
