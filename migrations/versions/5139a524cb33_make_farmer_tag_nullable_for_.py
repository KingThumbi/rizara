"""make farmer_tag nullable for procurement support

Revision ID: 5139a524cb33
Revises: e6b08903bacf
Create Date: 2026-04-27 16:42:53.908745
"""

from alembic import op
import sqlalchemy as sa


revision = "5139a524cb33"
down_revision = "e6b08903bacf"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "goat",
        "farmer_tag",
        existing_type=sa.String(length=64),
        nullable=True,
    )

    op.alter_column(
        "sheep",
        "farmer_tag",
        existing_type=sa.String(length=64),
        nullable=True,
    )

    op.alter_column(
        "cattle",
        "farmer_tag",
        existing_type=sa.String(length=64),
        nullable=True,
    )


def downgrade():
    op.alter_column(
        "cattle",
        "farmer_tag",
        existing_type=sa.String(length=64),
        nullable=False,
    )

    op.alter_column(
        "sheep",
        "farmer_tag",
        existing_type=sa.String(length=64),
        nullable=False,
    )

    op.alter_column(
        "goat",
        "farmer_tag",
        existing_type=sa.String(length=64),
        nullable=False,
    )