"""add line discount to invoice items

Revision ID: 78748b7158ff
Revises: 60383f3489ea
Create Date: 2026-05-03 16:10:30.537281

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '78748b7158ff'
down_revision = '60383f3489ea'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("invoice_item", sa.Column("gross_unit_price", sa.Numeric(14, 2), nullable=True))
    op.add_column("invoice_item", sa.Column("discount_per_unit", sa.Numeric(14, 2), nullable=True))
    op.add_column("invoice_item", sa.Column("discount_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("invoice_item", sa.Column("net_unit_price", sa.Numeric(14, 2), nullable=True))


def downgrade():
    op.drop_column("invoice_item", "net_unit_price")
    op.drop_column("invoice_item", "discount_amount")
    op.drop_column("invoice_item", "discount_per_unit")
    op.drop_column("invoice_item", "gross_unit_price")