"""ops_batches_sales_invoices_finance

Revision ID: faaa0326b1c6
Revises: ea75ebf5e230
Create Date: 2026-01-18 23:21:49.986928

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql



# revision identifiers, used by Alembic.
revision = 'faaa0326b1c6'
down_revision = 'ea75ebf5e230'
branch_labels = None
depends_on = None


def upgrade():
    # -------------------------
    # 1) Add columns to goat/sheep/cattle (BaseAnimal additions)
    # -------------------------
    for table in ("goat", "sheep", "cattle"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")))

            batch_op.add_column(sa.Column("aggregated_at", sa.DateTime(), nullable=True))
            batch_op.add_column(sa.Column("aggregated_by_user_id", sa.Integer(), nullable=True))

            batch_op.add_column(sa.Column("live_weight_kg", sa.Float(), nullable=True))
            batch_op.add_column(sa.Column("weight_method", sa.String(length=20), nullable=True))

            batch_op.add_column(sa.Column("purchase_price_per_head", sa.Float(), nullable=True))
            batch_op.add_column(sa.Column("purchase_currency", sa.String(length=10), nullable=False, server_default="KES"))

            batch_op.create_foreign_key(
                f"fk_{table}_aggregated_by_user",
                "user",
                ["aggregated_by_user_id"],
                ["id"],
            )

    # -------------------------
    # 2) Animal Event Ledger
    # -------------------------
    op.create_table(
        "animal_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("animal_type", sa.String(length=20), nullable=False),
        sa.Column("animal_id", postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("event_datetime", sa.DateTime(), nullable=False, server_default=sa.text("now()")),

        sa.Column("performed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("from_farmer_id", sa.Integer(), nullable=True),
        sa.Column("to_farmer_id", sa.Integer(), nullable=True),

        sa.Column("from_location", sa.String(length=120), nullable=True),
        sa.Column("to_location", sa.String(length=120), nullable=True),

        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("attachment_url", sa.String(length=255), nullable=True),

        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("verified_by_user_id", sa.Integer(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),

        sa.ForeignKeyConstraint(["performed_by_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["from_farmer_id"], ["farmer.id"]),
        sa.ForeignKeyConstraint(["to_farmer_id"], ["farmer.id"]),
    )

    # -------------------------
    # 3) Aggregation costs + animal health
    # -------------------------
    op.create_table(
        "aggregation_cost",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("aggregation_batch_id", sa.Integer(), nullable=False),
        sa.Column("cost_type", sa.String(length=30), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="KES"),
        sa.Column("incurred_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("paid_to", sa.String(length=120), nullable=True),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["aggregation_batch_id"], ["aggregation_batch.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
    )

    op.create_table(
        "animal_health_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("animal_type", sa.String(length=20), nullable=False),
        sa.Column("animal_id", postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("aggregation_batch_id", sa.Integer(), nullable=False),

        sa.Column("diagnosis", sa.String(length=200), nullable=True),
        sa.Column("treatment", sa.String(length=200), nullable=True),

        sa.Column("cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="KES"),

        sa.Column("treated_by", sa.String(length=120), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("notes", sa.Text(), nullable=True),

        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),

        sa.ForeignKeyConstraint(["aggregation_batch_id"], ["aggregation_batch.id"]),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["user.id"]),
    )

    # -------------------------
    # 4) Processing yield
    # -------------------------
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

        sa.ForeignKeyConstraint(["processing_batch_id"], ["processing_batch.id"]),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["user.id"]),
    )

    # -------------------------
    # 5) Buyer + batch sale
    # -------------------------
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

    op.create_table(
        "processing_batch_sale",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("processing_batch_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("buyer_id", sa.Integer(), nullable=False),
        sa.Column("total_sale_price", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="KES"),
        sa.Column("sale_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("sold_by_user_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["processing_batch_id"], ["processing_batch.id"]),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyer.id"]),
        sa.ForeignKeyConstraint(["sold_by_user_id"], ["user.id"]),
    )

    # -------------------------
    # 6) Invoices
    # -------------------------
    op.create_table(
        "invoice",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_number", sa.String(length=40), nullable=False, unique=True),

        sa.Column("buyer_id", sa.Integer(), nullable=False),
        sa.Column("processing_batch_sale_id", sa.Integer(), nullable=False, unique=True),

        sa.Column("issue_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("due_date", sa.Date(), nullable=True),

        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("subtotal", sa.Float(), nullable=False, server_default="0"),
        sa.Column("tax", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total", sa.Float(), nullable=False, server_default="0"),

        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("terms", sa.Text(), nullable=True),

        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),

        sa.ForeignKeyConstraint(["buyer_id"], ["buyer.id"]),
        sa.ForeignKeyConstraint(["processing_batch_sale_id"], ["processing_batch_sale.id"]),
    )

    op.create_table(
        "invoice_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_id", sa.Integer(), nullable=False),

        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("line_total", sa.Float(), nullable=False, server_default="0"),

        sa.ForeignKeyConstraint(["invoice_id"], ["invoice.id"]),
    )

    # -------------------------
    # 7) Finance: vendors, expense categories, expenses, assets
    # -------------------------
    op.create_table(
        "vendor",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("email", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "expense_category",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=80), nullable=False, unique=True),
        sa.Column("expense_class", sa.String(length=20), nullable=False, server_default="overhead"),
    )

    op.create_table(
        "expense",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("expense_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),

        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("vendor_id", sa.Integer(), nullable=True),

        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="KES"),

        sa.Column("payment_method", sa.String(length=30), nullable=True),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("cost_center", sa.String(length=120), nullable=True),

        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("attachment_url", sa.String(length=255), nullable=True),

        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),

        sa.ForeignKeyConstraint(["category_id"], ["expense_category.id"]),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendor.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
    )

    op.create_table(
        "asset",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("asset_type", sa.String(length=60), nullable=False),
        sa.Column("ownership_type", sa.String(length=20), nullable=False, server_default="owned"),

        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("purchase_cost", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="KES"),

        sa.Column("location", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),

        sa.Column("vendor_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),

        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendor.id"]),
    )

    op.create_table(
        "asset_maintenance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), nullable=False),

        sa.Column("maintenance_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="KES"),

        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("attachment_url", sa.String(length=255), nullable=True),

        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),

        sa.ForeignKeyConstraint(["asset_id"], ["asset.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
    )


def downgrade():
    # Drop in strict reverse order
    op.drop_table("asset_maintenance")
    op.drop_table("asset")
    op.drop_table("expense")
    op.drop_table("expense_category")
    op.drop_table("vendor")

    op.drop_table("invoice_item")
    op.drop_table("invoice")
    op.drop_table("processing_batch_sale")
    op.drop_table("buyer")

    op.drop_table("processing_yield")
    op.drop_table("animal_health_event")
    op.drop_table("aggregation_cost")
    op.drop_table("animal_event")

    for table in ("cattle", "sheep", "goat"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(f"fk_{table}_aggregated_by_user", type_="foreignkey")
            batch_op.drop_column("purchase_currency")
            batch_op.drop_column("purchase_price_per_head")
            batch_op.drop_column("weight_method")
            batch_op.drop_column("live_weight_kg")
            batch_op.drop_column("aggregated_by_user_id")
            batch_op.drop_column("aggregated_at")
            batch_op.drop_column("is_active")
