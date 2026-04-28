"""add receipt number to invoice payments

Revision ID: 3939f2bc0031
Revises: bd9576e13d73
Create Date: 2026-04-28 22:50:25.949813

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3939f2bc0031'
down_revision = 'bd9576e13d73'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "invoice_payments",
        sa.Column("receipt_number", sa.String(length=40), nullable=True),
    )

    op.execute("""
        UPDATE invoice_payments
        SET receipt_number = 'RCT-' || TO_CHAR(COALESCE(paid_at, created_at, NOW()), 'YYYY') || '-' || LPAD(id::text, 5, '0')
        WHERE receipt_number IS NULL
    """)

    op.alter_column(
        "invoice_payments",
        "receipt_number",
        existing_type=sa.String(length=40),
        nullable=False,
    )

    op.create_index(
        "ix_invoice_payments_receipt_number",
        "invoice_payments",
        ["receipt_number"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_invoice_payments_receipt_number", table_name="invoice_payments")
    op.drop_column("invoice_payments", "receipt_number")