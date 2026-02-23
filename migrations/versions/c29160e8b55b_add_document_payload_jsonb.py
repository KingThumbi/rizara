"""add document payload jsonb

Revision ID: c29160e8b55b
Revises: 8f1bf7812d62
Create Date: 2026-02-20 21:11:00.539643

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "c29160e8b55b"
down_revision = "8f1bf7812d62"
branch_labels = None
depends_on = None


def upgrade():
    # Add JSONB payload container for contract terms and other document data
    op.add_column(
        "document",
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade():
    # Safe downgrade: don't fail if the column was never created (e.g. earlier bad revision)
    op.execute("ALTER TABLE document DROP COLUMN IF EXISTS payload")