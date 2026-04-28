"""add invoice payments

Revision ID: bd9576e13d73
Revises: a5912f1eef67
Create Date: 2026-04-28 20:21:11.139790
"""

from alembic import op
import sqlalchemy as sa


revision = "bd9576e13d73"
down_revision = "a5912f1eef67"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "invoice_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("method", sa.String(50), nullable=True),
        sa.Column("reference", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoice.id"],
            ondelete="CASCADE",
            name="fk_invoice_payments_invoice_id",
        ),
    )

    op.create_index(
        "ix_invoice_payments_invoice_id",
        "invoice_payments",
        ["invoice_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_invoice_payments_invoice_id",
        table_name="invoice_payments",
    )

    op.drop_table("invoice_payments")