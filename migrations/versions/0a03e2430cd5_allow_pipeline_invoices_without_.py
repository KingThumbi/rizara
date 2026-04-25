"""allow pipeline invoices without processing batch sale

Revision ID: 0a03e2430cd5
Revises: 974db832714b
Create Date: 2026-04-25 17:53:37.015084

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0a03e2430cd5'
down_revision = '974db832714b'
branch_labels = None
depends_on = None



def upgrade():
    op.alter_column(
        "invoice",
        "processing_batch_sale_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade():
    op.alter_column(
        "invoice",
        "processing_batch_sale_id",
        existing_type=sa.Integer(),
        nullable=False,
    )