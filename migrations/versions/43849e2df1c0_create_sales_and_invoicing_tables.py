"""create_sales_and_invoicing_tables

Revision ID: 43849e2df1c0
Revises: 6e2c50c103f2
Create Date: 2026-01-19 21:01:59.728149

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '43849e2df1c0'
down_revision = '6e2c50c103f2'
branch_labels = None
depends_on = None


def upgrade():
    # =========================
    # buyer
    # =========================
    op.create_table(
        "buyer",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("email", sa.String(length=120), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("tax_pin", sa.String(length=60), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )

    # =========================
    # processing_yield
    # one per processing_batch
    # =========================
    op.create_table(
        "processing_yield",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("processing_batch_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("total_carcass_weight_kg", sa.Float(), nullable=False),
        sa.Column("parts_included_in_batch_sale", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("parts_sold_separately", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("parts_notes", sa.Text(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["processing_batch_id"], ["processing_batch.id"], name="fk_processing_yield_processing_batch"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["user.id"], name="fk_processing_yield_recorded_by_user"),
    )

    # =========================
    # processing_batch_sale
    # one per processing_batch
    # =========================
    op.create_table(
        "processing_batch_sale",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("processing_batch_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("buyer_id", sa.Integer(), nullable=False),
        sa.Column("total_sale_price", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="KES"),
        sa.Column("sale_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["processing_batch_id"], ["processing_batch.id"], name="fk_processing_batch_sale_processing_batch"),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyer.id"], name="fk_processing_batch_sale_buyer"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["user.id"], name="fk_processing_batch_sale_recorded_by_user"),
    )

    # =========================
    # invoice
    # one per processing_batch_sale
    # =========================
    op.create_table(
        "invoice",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_number", sa.String(length=40), nullable=False, unique=True),
        sa.Column("buyer_id", sa.Integer(), nullable=False),
        sa.Column("processing_batch_sale_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("issue_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("subtotal", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("tax", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("total", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("terms", sa.Text(), nullable=True),
        sa.Column("issued_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyer.id"], name="fk_invoice_buyer"),
        sa.ForeignKeyConstraint(["processing_batch_sale_id"], ["processing_batch_sale.id"], name="fk_invoice_processing_batch_sale"),
        sa.ForeignKeyConstraint(["issued_by_user_id"], ["user.id"], name="fk_invoice_issued_by_user"),
    )

    # =========================
    # invoice_item
    # =========================
    op.create_table(
        "invoice_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False, server_default=sa.text("1")),
        sa.Column("unit_price", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("line_total", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoice.id"], name="fk_invoice_item_invoice"),
    )


def downgrade():
    op.drop_table("invoice_item")
    op.drop_table("invoice")
    op.drop_table("processing_batch_sale")
    op.drop_table("processing_yield")
    op.drop_table("buyer")
