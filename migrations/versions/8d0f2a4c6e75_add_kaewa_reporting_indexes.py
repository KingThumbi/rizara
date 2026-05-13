"""add kaewa reporting indexes

Revision ID: 8d0f2a4c6e75
Revises: 7c9e1f3a5b64
Create Date: 2026-05-14 00:00:00.000000
"""
from alembic import op


revision = "8d0f2a4c6e75"
down_revision = "7c9e1f3a5b64"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_stakeholder_category_status_location",
        "stakeholder",
        ["category", "status", "county", "sub_county"],
    )
    op.create_index(
        "ix_field_livestock_intake_status_animal_created",
        "field_livestock_intake",
        ["intake_status", "animal_type", "created_at"],
    )
    op.create_index(
        "ix_rural_service_sale_status_date_payment",
        "rural_service_sale",
        ["status", "sale_date", "payment_method"],
    )
    op.create_index(
        "ix_rural_service_stock_movement_product_created",
        "rural_service_stock_movement",
        ["product_id", "created_at"],
    )


def downgrade():
    op.drop_index("ix_rural_service_stock_movement_product_created", table_name="rural_service_stock_movement")
    op.drop_index("ix_rural_service_sale_status_date_payment", table_name="rural_service_sale")
    op.drop_index("ix_field_livestock_intake_status_animal_created", table_name="field_livestock_intake")
    op.drop_index("ix_stakeholder_category_status_location", table_name="stakeholder")
