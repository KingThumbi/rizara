"""add unified procurement inventory lots and invoice stock links

Revision ID: 5f986bcac231
Revises: be90dec940c1
Create Date: 2026-04-27 10:44:09.650611
"""

from alembic import op
import sqlalchemy as sa


revision = "5f986bcac231"
down_revision = "be90dec940c1"
branch_labels = None
depends_on = None


def upgrade():
    # =====================================================
    # Procurement Sources
    # Farmers = primary supply, Markets = supplementary
    # =====================================================
    op.create_table(
        "procurement_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("location", sa.String(length=160), nullable=True),
        sa.Column("county", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "source_type in ('farmer','market')",
            name="ck_procurement_source_type",
        ),
    )

    op.create_index(
        "ix_procurement_sources_source_type",
        "procurement_sources",
        ["source_type"],
    )
    op.create_index(
        "ix_procurement_sources_name",
        "procurement_sources",
        ["name"],
    )

    # =====================================================
    # Procurement Records
    # Links source → aggregation batch → animal generation
    # =====================================================
    op.create_table(
        "procurement_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("aggregation_batch_id", sa.Integer(), nullable=True),
        sa.Column("animal_type", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("estimated_total_weight_kg", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("estimated_avg_weight_kg", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "animal_type in ('goat','sheep','cattle')",
            name="ck_procurement_record_animal_type",
        ),
        sa.CheckConstraint(
            "status in ('draft','confirmed','received','cancelled')",
            name="ck_procurement_record_status",
        ),
        sa.CheckConstraint("quantity >= 0", name="ck_procurement_record_quantity_non_negative"),
        sa.CheckConstraint("unit_price >= 0", name="ck_procurement_record_unit_price_non_negative"),
        sa.CheckConstraint("total_cost >= 0", name="ck_procurement_record_total_cost_non_negative"),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["procurement_sources.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["aggregation_batch_id"],
            ["aggregation_batch.id"],
            ondelete="SET NULL",
        ),
    )

    op.create_index(
        "ix_procurement_records_source_id",
        "procurement_records",
        ["source_id"],
    )
    op.create_index(
        "ix_procurement_records_aggregation_batch_id",
        "procurement_records",
        ["aggregation_batch_id"],
    )
    op.create_index(
        "ix_procurement_records_animal_type",
        "procurement_records",
        ["animal_type"],
    )
    op.create_index(
        "ix_procurement_records_status",
        "procurement_records",
        ["status"],
    )

    # =====================================================
    # Animal source tracking
    # Goat / Sheep / Cattle can now trace back to procurement
    # =====================================================
    op.add_column(
        "goat",
        sa.Column("procurement_record_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "goat",
        sa.Column("source_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "goat",
        sa.Column("source_name", sa.String(length=160), nullable=True),
    )
    op.create_index("ix_goat_procurement_record_id", "goat", ["procurement_record_id"])
    op.create_foreign_key(
        "fk_goat_procurement_record",
        "goat",
        "procurement_records",
        ["procurement_record_id"],
        ["id"],
    )

    op.add_column(
        "sheep",
        sa.Column("procurement_record_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "sheep",
        sa.Column("source_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "sheep",
        sa.Column("source_name", sa.String(length=160), nullable=True),
    )
    op.create_index("ix_sheep_procurement_record_id", "sheep", ["procurement_record_id"])
    op.create_foreign_key(
        "fk_sheep_procurement_record",
        "sheep",
        "procurement_records",
        ["procurement_record_id"],
        ["id"],
    )

    op.add_column(
        "cattle",
        sa.Column("procurement_record_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "cattle",
        sa.Column("source_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "cattle",
        sa.Column("source_name", sa.String(length=160), nullable=True),
    )
    op.create_index("ix_cattle_procurement_record_id", "cattle", ["procurement_record_id"])
    op.create_foreign_key(
        "fk_cattle_procurement_record",
        "cattle",
        "procurement_records",
        ["procurement_record_id"],
        ["id"],
    )

    # =====================================================
    # Inventory Lot
    # Processing yield becomes saleable inventory
    # =====================================================
    op.create_table(
        "inventory_lot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("processing_batch_id", sa.Integer(), nullable=False),
        sa.Column("batch_number", sa.String(length=80), nullable=False),
        sa.Column("product_name", sa.String(length=160), nullable=False),
        sa.Column("product_type", sa.String(length=80), nullable=True),
        sa.Column("animal_type", sa.String(length=20), nullable=False),
        sa.Column("quantity_kg", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("available_kg", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("unit", sa.String(length=20), nullable=False, server_default="kg"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="available"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "animal_type in ('goat','sheep','cattle')",
            name="ck_inventory_lot_animal_type",
        ),
        sa.CheckConstraint("quantity_kg >= 0", name="ck_inventory_lot_quantity_non_negative"),
        sa.CheckConstraint("available_kg >= 0", name="ck_inventory_lot_available_non_negative"),
        sa.CheckConstraint(
            "available_kg <= quantity_kg",
            name="ck_inventory_lot_available_not_more_than_quantity",
        ),
        sa.CheckConstraint(
            "status in ('available','partially_sold','sold_out','adjusted','expired')",
            name="ck_inventory_lot_status",
        ),
        sa.ForeignKeyConstraint(
            ["processing_batch_id"],
            ["processing_batch.id"],
            ondelete="CASCADE",
        ),
    )

    op.create_index("ix_inventory_lot_processing_batch_id", "inventory_lot", ["processing_batch_id"])
    op.create_index("ix_inventory_lot_batch_number", "inventory_lot", ["batch_number"])
    op.create_index("ix_inventory_lot_animal_type", "inventory_lot", ["animal_type"])
    op.create_index("ix_inventory_lot_status", "inventory_lot", ["status"])

    # =====================================================
    # Invoice Item → Inventory Lot
    # Enables invoicing from stock
    # =====================================================
    op.add_column(
        "invoice_item",
        sa.Column("inventory_lot_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "invoice_item",
        sa.Column("unit", sa.String(length=20), nullable=False, server_default="kg"),
    )

    op.create_index(
        "ix_invoice_item_inventory_lot_id",
        "invoice_item",
        ["inventory_lot_id"],
    )
    op.create_foreign_key(
        "fk_invoice_item_inventory_lot",
        "invoice_item",
        "inventory_lot",
        ["inventory_lot_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint("fk_invoice_item_inventory_lot", "invoice_item", type_="foreignkey")
    op.drop_index("ix_invoice_item_inventory_lot_id", table_name="invoice_item")
    op.drop_column("invoice_item", "unit")
    op.drop_column("invoice_item", "inventory_lot_id")

    op.drop_index("ix_inventory_lot_status", table_name="inventory_lot")
    op.drop_index("ix_inventory_lot_animal_type", table_name="inventory_lot")
    op.drop_index("ix_inventory_lot_batch_number", table_name="inventory_lot")
    op.drop_index("ix_inventory_lot_processing_batch_id", table_name="inventory_lot")
    op.drop_table("inventory_lot")

    op.drop_constraint("fk_cattle_procurement_record", "cattle", type_="foreignkey")
    op.drop_index("ix_cattle_procurement_record_id", table_name="cattle")
    op.drop_column("cattle", "source_name")
    op.drop_column("cattle", "source_type")
    op.drop_column("cattle", "procurement_record_id")

    op.drop_constraint("fk_sheep_procurement_record", "sheep", type_="foreignkey")
    op.drop_index("ix_sheep_procurement_record_id", table_name="sheep")
    op.drop_column("sheep", "source_name")
    op.drop_column("sheep", "source_type")
    op.drop_column("sheep", "procurement_record_id")

    op.drop_constraint("fk_goat_procurement_record", "goat", type_="foreignkey")
    op.drop_index("ix_goat_procurement_record_id", table_name="goat")
    op.drop_column("goat", "source_name")
    op.drop_column("goat", "source_type")
    op.drop_column("goat", "procurement_record_id")

    op.drop_index("ix_procurement_records_status", table_name="procurement_records")
    op.drop_index("ix_procurement_records_animal_type", table_name="procurement_records")
    op.drop_index("ix_procurement_records_aggregation_batch_id", table_name="procurement_records")
    op.drop_index("ix_procurement_records_source_id", table_name="procurement_records")
    op.drop_table("procurement_records")

    op.drop_index("ix_procurement_sources_name", table_name="procurement_sources")
    op.drop_index("ix_procurement_sources_source_type", table_name="procurement_sources")
    op.drop_table("procurement_sources")