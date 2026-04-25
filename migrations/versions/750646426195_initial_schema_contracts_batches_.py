"""initial schema: contracts batches outputs sales payments

Revision ID: 750646426195
Revises: 3af2009e4f8a
Create Date: 2026-04-21 21:52:39.031146
"""
from alembic import op
import sqlalchemy as sa


revision = "750646426195"
down_revision = "3af2009e4f8a"
branch_labels = None
depends_on = None


def upgrade():
    # ---------------------------------------------------------
    # contracts
    # ---------------------------------------------------------
    op.create_table(
        "contracts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contract_number", sa.String(50), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("contract_date", sa.Date(), nullable=False),
        sa.Column("delivery_date", sa.Date()),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("currency", sa.String(10), nullable=False, server_default="USD"),
        sa.Column("price_basis", sa.String(100)),
        sa.Column("payment_terms", sa.Text()),
        sa.Column("delivery_terms", sa.Text()),
        sa.Column("destination_country", sa.String(100)),
        sa.Column("required_prepayment_percent", sa.Numeric(8, 2)),
        sa.Column("required_prepayment_amount", sa.Numeric(14, 2)),
        sa.Column("contracted_quantity_kg", sa.Numeric(14, 2)),
        sa.Column("contracted_value", sa.Numeric(14, 2)),
        sa.Column("product_type", sa.String(120)),
        sa.Column("quality_spec", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.Integer()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("contract_number", name="uq_contracts_number"),
    )

    op.create_index("ix_contracts_customer", "contracts", ["customer_id"])
    op.create_index("ix_contracts_status", "contracts", ["status"])

    # ---------------------------------------------------------
    # contract_items
    # ---------------------------------------------------------
    op.create_table(
        "contract_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("product_name", sa.String(120), nullable=False),
        sa.Column("product_code", sa.String(50)),
        sa.Column("unit_of_measure", sa.String(20), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 2), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("quality_spec", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], name="fk_ci_contract"),
    )

    op.create_index("ix_ci_contract", "contract_items", ["contract_id"])

    # ---------------------------------------------------------
    # processing_batches
    # ---------------------------------------------------------
    op.create_table(
        "processing_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_number", sa.String(50), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("processing_date", sa.Date()),
        sa.Column("source_type", sa.String(30)),
        sa.Column("source_reference_id", sa.Integer()),
        sa.Column("planned_input_qty", sa.Numeric(14, 2)),
        sa.Column("actual_input_qty", sa.Numeric(14, 2)),
        sa.Column("output_qty", sa.Numeric(14, 2)),
        sa.Column("yield_percentage", sa.Numeric(8, 2)),
        sa.Column("processing_authorized", sa.Boolean(), server_default=sa.false()),
        sa.Column("authorization_status", sa.String(30), server_default="pending"),
        sa.Column("authorization_note", sa.Text()),
        sa.Column("authorized_at", sa.DateTime()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.Integer()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], name="fk_pb_contract"),
        sa.UniqueConstraint("batch_number", name="uq_pb_number"),
    )

    op.create_index("ix_pb_contract", "processing_batches", ["contract_id"])
    op.create_index("ix_pb_status", "processing_batches", ["status"])

    # ---------------------------------------------------------
    # processing_batch_outputs
    # ---------------------------------------------------------
    op.create_table(
        "processing_batch_outputs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("processing_batch_id", sa.Integer(), nullable=False),
        sa.Column("product_name", sa.String(120), nullable=False),
        sa.Column("product_code", sa.String(50)),
        sa.Column("quantity", sa.Numeric(14, 2), nullable=False),
        sa.Column("unit_of_measure", sa.String(20), nullable=False),
        sa.Column("grade", sa.String(50)),
        sa.Column("destination_type", sa.String(30), server_default="contract_sale"),
        sa.Column("notes", sa.Text()),
        sa.ForeignKeyConstraint(["processing_batch_id"], ["processing_batches.id"], name="fk_pbo_batch"),
    )

    op.create_index("ix_pbo_batch", "processing_batch_outputs", ["processing_batch_id"])

    # ---------------------------------------------------------
    # sales
    # ---------------------------------------------------------
    op.create_table(
        "sales",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sale_number", sa.String(50), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("sale_date", sa.Date(), nullable=False),
        sa.Column("invoice_type", sa.String(20), server_default="commercial"),
        sa.Column("status", sa.String(30), server_default="draft"),
        sa.Column("currency", sa.String(10), server_default="USD"),
        sa.Column("subtotal", sa.Numeric(14, 2), server_default="0"),
        sa.Column("discount", sa.Numeric(14, 2), server_default="0"),
        sa.Column("tax_amount", sa.Numeric(14, 2), server_default="0"),
        sa.Column("total_amount", sa.Numeric(14, 2), server_default="0"),
        sa.Column("prepaid_amount", sa.Numeric(14, 2), server_default="0"),
        sa.Column("amount_paid", sa.Numeric(14, 2), server_default="0"),
        sa.Column("balance_due", sa.Numeric(14, 2), server_default="0"),
        sa.Column("payment_status", sa.String(30), server_default="unpaid"),
        sa.Column("processing_authorized", sa.Boolean(), server_default=sa.false()),
        sa.Column("authorized_at", sa.DateTime()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.Integer()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], name="fk_sales_contract"),
        sa.UniqueConstraint("sale_number", name="uq_sales_number"),
    )

    op.create_index("ix_sales_contract", "sales", ["contract_id"])
    op.create_index("ix_sales_customer", "sales", ["customer_id"])
    op.create_index("ix_sales_status", "sales", ["status"])
    op.create_index("ix_sales_pay_status", "sales", ["payment_status"])

    # ---------------------------------------------------------
    # sale_items
    # ---------------------------------------------------------
    op.create_table(
        "sale_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sale_id", sa.Integer(), nullable=False),
        sa.Column("contract_item_id", sa.Integer()),
        sa.Column("processing_batch_output_id", sa.Integer()),
        sa.Column("product_name", sa.String(120), nullable=False),
        sa.Column("product_code", sa.String(50)),
        sa.Column("quantity", sa.Numeric(14, 2), nullable=False),
        sa.Column("unit_of_measure", sa.String(20), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], name="fk_si_sale"),
        sa.ForeignKeyConstraint(["contract_item_id"], ["contract_items.id"], name="fk_si_contract_item"),
        sa.ForeignKeyConstraint(["processing_batch_output_id"], ["processing_batch_outputs.id"], name="fk_si_output"),
    )

    op.create_index("ix_si_sale", "sale_items", ["sale_id"])
    op.create_index("ix_si_contract_item", "sale_items", ["contract_item_id"])
    op.create_index("ix_si_output", "sale_items", ["processing_batch_output_id"])

    # ---------------------------------------------------------
    # sale_payments
    # ---------------------------------------------------------
    op.create_table(
        "sale_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sale_id", sa.Integer(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("payment_type", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("payment_method", sa.String(30)),
        sa.Column("reference_number", sa.String(100)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.Integer()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], name="fk_sp_sale"),
    )

    op.create_index("ix_sp_sale", "sale_payments", ["sale_id"])
    op.create_index("ix_sp_type", "sale_payments", ["payment_type"])


def downgrade():
    op.drop_table("sale_payments")
    op.drop_table("sale_items")
    op.drop_table("sales")
    op.drop_table("processing_batch_outputs")
    op.drop_table("processing_batches")
    op.drop_table("contract_items")
    op.drop_table("contracts")