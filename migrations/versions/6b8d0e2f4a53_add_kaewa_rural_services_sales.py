"""add kaewa rural services sales

Revision ID: 6b8d0e2f4a53
Revises: 5a7b9c1d3e42
Create Date: 2026-05-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "6b8d0e2f4a53"
down_revision = "5a7b9c1d3e42"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rural_service_sale",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("sale_number", sa.String(length=60), nullable=False),
        sa.Column("stakeholder_id", sa.Integer(), nullable=True),
        sa.Column("buyer_name", sa.String(length=180), nullable=True),
        sa.Column("buyer_phone", sa.String(length=30), nullable=True),
        sa.Column("sale_date", sa.Date(), nullable=False),
        sa.Column("payment_method", sa.String(length=20), nullable=False),
        sa.Column("payment_reference", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["stakeholder_id"], ["stakeholder.id"]),
    )
    op.create_index("ix_rural_service_sale_uuid", "rural_service_sale", ["uuid"], unique=True)
    op.create_index("ix_rural_service_sale_sale_number", "rural_service_sale", ["sale_number"], unique=True)
    op.create_index("ix_rural_service_sale_stakeholder_id", "rural_service_sale", ["stakeholder_id"])
    op.create_index("ix_rural_service_sale_sale_date", "rural_service_sale", ["sale_date"])
    op.create_index("ix_rural_service_sale_payment_method", "rural_service_sale", ["payment_method"])
    op.create_index("ix_rural_service_sale_payment_reference", "rural_service_sale", ["payment_reference"])
    op.create_index("ix_rural_service_sale_status", "rural_service_sale", ["status"])
    op.create_index("ix_rural_service_sale_created_by_user_id", "rural_service_sale", ["created_by_user_id"])
    op.create_index("ix_rural_service_sale_created_at", "rural_service_sale", ["created_at"])

    op.create_table(
        "rural_service_sale_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sale_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 2), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["rural_service_product.id"]),
        sa.ForeignKeyConstraint(["sale_id"], ["rural_service_sale.id"]),
    )
    op.create_index("ix_rural_service_sale_item_sale_id", "rural_service_sale_item", ["sale_id"])
    op.create_index("ix_rural_service_sale_item_product_id", "rural_service_sale_item", ["product_id"])


def downgrade():
    op.drop_table("rural_service_sale_item")
    op.drop_table("rural_service_sale")
