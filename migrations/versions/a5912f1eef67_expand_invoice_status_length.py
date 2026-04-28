"""expand invoice status length

Revision ID: a5912f1eef67
Revises: 58e5621d199d
Create Date: 2026-04-28 18:14:45.661486

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a5912f1eef67'
down_revision = '58e5621d199d'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "invoice",
        "status",
        existing_type=sa.String(length=6),
        type_=sa.String(length=30),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        "invoice",
        "status",
        existing_type=sa.String(length=30),
        type_=sa.String(length=6),
        existing_nullable=False,
    )