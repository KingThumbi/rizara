"""Add accepted_terms fields to user (fix)

Revision ID: ba9643084eed
Revises: a02201e1ebe0
Create Date: 2026-01-23 18:19:41.730584

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ba9643084eed'
down_revision = 'a02201e1ebe0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user",
        sa.Column("accepted_terms", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("user", sa.Column("accepted_terms_at", sa.DateTime(), nullable=True))
    op.add_column("user", sa.Column("terms_version", sa.String(length=20), nullable=True))

    op.alter_column("user", "accepted_terms", server_default=None)


def downgrade():
    op.drop_column("user", "terms_version")
    op.drop_column("user", "accepted_terms_at")
    op.drop_column("user", "accepted_terms")