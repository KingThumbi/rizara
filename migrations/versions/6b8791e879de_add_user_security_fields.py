"""Add user security fields

Revision ID: 6b8791e879de
Revises: ca0a3f3f842f
Create Date: 2026-01-22 15:27:13.501197
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "6b8791e879de"
down_revision = "ca0a3f3f842f"
branch_labels = None
depends_on = None


def upgrade():
    # 1) Add columns with safe server defaults so existing rows get values
    op.add_column(
        "user",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "user",
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("user", sa.Column("locked_until", sa.DateTime(), nullable=True))
    op.add_column(
        "user",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("user", sa.Column("password_changed_at", sa.DateTime(), nullable=True))
    op.add_column("user", sa.Column("last_login_at", sa.DateTime(), nullable=True))

    op.add_column(
        "user",
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )

    # 2) Remove server defaults (optional, but clean) — app controls values going forward
    op.alter_column("user", "is_active", server_default=None)
    op.alter_column("user", "failed_login_attempts", server_default=None)
    op.alter_column("user", "must_change_password", server_default=None)
    op.alter_column("user", "updated_at", server_default=None)


def downgrade():
    op.drop_column("user", "updated_at")
    op.drop_column("user", "last_login_at")
    op.drop_column("user", "password_changed_at")
    op.drop_column("user", "must_change_password")
    op.drop_column("user", "locked_until")
    op.drop_column("user", "failed_login_attempts")
    op.drop_column("user", "is_active")
