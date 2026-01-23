"""Add user terms acceptance fields

Revision ID: a02201e1ebe0
Revises: db7c42f6dc55
Create Date: 2026-01-23 17:19:04.137460

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a02201e1ebe0"
down_revision = "db7c42f6dc55"
branch_labels = None
depends_on = None


def upgrade():
    # Add Terms acceptance fields to user table (SAFE for existing rows)
    op.add_column(
        "user",
        sa.Column(
            "accepted_terms",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("user", sa.Column("accepted_terms_at", sa.DateTime(), nullable=True))
    op.add_column("user", sa.Column("terms_version", sa.String(length=20), nullable=True))

    # Optional cleanup: drop server default after column exists
    op.alter_column("user", "accepted_terms", server_default=None)


def downgrade():
    op.drop_column("user", "terms_version")
    op.drop_column("user", "accepted_terms_at")
    op.drop_column("user", "accepted_terms")
