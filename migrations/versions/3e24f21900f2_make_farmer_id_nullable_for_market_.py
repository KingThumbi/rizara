"""make farmer_id nullable for market procurement

Revision ID: 3e24f21900f2
Revises: 5139a524cb33
Create Date: 2026-04-27 17:03:31.226573

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '3e24f21900f2'
down_revision = '5139a524cb33'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "goat",
        "farmer_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    op.alter_column(
        "sheep",
        "farmer_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    op.alter_column(
        "cattle",
        "farmer_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade():
    op.alter_column("cattle", "farmer_id", nullable=False)
    op.alter_column("sheep", "farmer_id", nullable=False)
    op.alter_column("goat", "farmer_id", nullable=False)