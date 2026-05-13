"""add kaewa rural services inventory

Revision ID: 5a7b9c1d3e42
Revises: 4e6f8a0b2c31
Create Date: 2026-05-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "5a7b9c1d3e42"
down_revision = "4e6f8a0b2c31"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rural_service_product",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("sku", sa.String(length=80), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("reorder_level", sa.Numeric(14, 2), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_rural_service_product_uuid", "rural_service_product", ["uuid"], unique=True)
    op.create_index("ix_rural_service_product_category", "rural_service_product", ["category"])
    op.create_index("ix_rural_service_product_unit", "rural_service_product", ["unit"])
    op.create_index("ix_rural_service_product_sku", "rural_service_product", ["sku"], unique=True)
    op.create_index("ix_rural_service_product_active", "rural_service_product", ["active"])
    op.create_index("ix_rural_service_product_created_at", "rural_service_product", ["created_at"])

    op.create_table(
        "rural_service_stock_movement",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("movement_type", sa.String(length=40), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 2), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("supplier_name", sa.String(length=180), nullable=True),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["rural_service_product.id"]),
    )
    op.create_index(
        "ix_rural_service_stock_movement_uuid",
        "rural_service_stock_movement",
        ["uuid"],
        unique=True,
    )
    op.create_index(
        "ix_rural_service_stock_movement_product_id",
        "rural_service_stock_movement",
        ["product_id"],
    )
    op.create_index(
        "ix_rural_service_stock_movement_movement_type",
        "rural_service_stock_movement",
        ["movement_type"],
    )
    op.create_index(
        "ix_rural_service_stock_movement_reference",
        "rural_service_stock_movement",
        ["reference"],
    )
    op.create_index(
        "ix_rural_service_stock_movement_created_by_user_id",
        "rural_service_stock_movement",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_rural_service_stock_movement_created_at",
        "rural_service_stock_movement",
        ["created_at"],
    )


def downgrade():
    op.drop_table("rural_service_stock_movement")
    op.drop_table("rural_service_product")
