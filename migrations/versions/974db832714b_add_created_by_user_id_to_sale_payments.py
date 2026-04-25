"""add created_by_user_id to sale_payments

Revision ID: 974db832714b
Revises: ec6e3639afa1
Create Date: 2026-04-25 15:13:42.289526

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '974db832714b'
down_revision = 'ec6e3639afa1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "sale_payments",
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
    )

def downgrade():
    op.drop_column("sale_payments", "created_by_user_id")