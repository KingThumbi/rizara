"""add kaewa daily reconciliation

Revision ID: 7c9e1f3a5b64
Revises: 6b8d0e2f4a53
Create Date: 2026-05-14 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "7c9e1f3a5b64"
down_revision = "6b8d0e2f4a53"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "kaewa_daily_reconciliation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("reconciliation_date", sa.Date(), nullable=False),
        sa.Column("office_location", sa.String(length=120), nullable=False),
        sa.Column("opening_cash", sa.Numeric(14, 2), nullable=True),
        sa.Column("cash_sales_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("mpesa_sales_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("bank_sales_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("credit_sales_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("internal_sales_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("expected_cash_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("counted_cash", sa.Numeric(14, 2), nullable=True),
        sa.Column("cash_variance", sa.Numeric(14, 2), nullable=True),
        sa.Column("stock_variance_notes", sa.Text(), nullable=True),
        sa.Column("general_notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("prepared_by_user_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("prepared_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["prepared_by_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["user.id"]),
    )
    op.create_index("ix_kaewa_daily_reconciliation_uuid", "kaewa_daily_reconciliation", ["uuid"], unique=True)
    op.create_index(
        "ix_kaewa_daily_reconciliation_reconciliation_date",
        "kaewa_daily_reconciliation",
        ["reconciliation_date"],
        unique=True,
    )
    op.create_index("ix_kaewa_daily_reconciliation_office_location", "kaewa_daily_reconciliation", ["office_location"])
    op.create_index("ix_kaewa_daily_reconciliation_status", "kaewa_daily_reconciliation", ["status"])
    op.create_index(
        "ix_kaewa_daily_reconciliation_prepared_by_user_id",
        "kaewa_daily_reconciliation",
        ["prepared_by_user_id"],
    )
    op.create_index(
        "ix_kaewa_daily_reconciliation_reviewed_by_user_id",
        "kaewa_daily_reconciliation",
        ["reviewed_by_user_id"],
    )
    op.create_index("ix_kaewa_daily_reconciliation_prepared_at", "kaewa_daily_reconciliation", ["prepared_at"])
    op.create_index("ix_kaewa_daily_reconciliation_reviewed_at", "kaewa_daily_reconciliation", ["reviewed_at"])
    op.create_index("ix_kaewa_daily_reconciliation_created_at", "kaewa_daily_reconciliation", ["created_at"])

    op.create_table(
        "kaewa_daily_reconciliation_line",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reconciliation_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("system_stock_qty", sa.Numeric(14, 2), nullable=False),
        sa.Column("counted_stock_qty", sa.Numeric(14, 2), nullable=True),
        sa.Column("variance_qty", sa.Numeric(14, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["rural_service_product.id"]),
        sa.ForeignKeyConstraint(["reconciliation_id"], ["kaewa_daily_reconciliation.id"]),
    )
    op.create_index(
        "ix_kaewa_daily_reconciliation_line_reconciliation_id",
        "kaewa_daily_reconciliation_line",
        ["reconciliation_id"],
    )
    op.create_index(
        "ix_kaewa_daily_reconciliation_line_product_id",
        "kaewa_daily_reconciliation_line",
        ["product_id"],
    )


def downgrade():
    op.drop_table("kaewa_daily_reconciliation_line")
    op.drop_table("kaewa_daily_reconciliation")
