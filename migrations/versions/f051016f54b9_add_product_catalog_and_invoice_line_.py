"""add product catalog and invoice line discounts

Revision ID: f051016f54b9
Revises: 78748b7158ff
Create Date: 2026-05-03 20:47:58.087968

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f051016f54b9'
down_revision = '78748b7158ff'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_catalog",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=True),
        sa.Column("animal_type", sa.String(length=40), nullable=False),
        sa.Column("product_type", sa.String(length=80), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False, server_default="kg"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_product_catalog_name", "product_catalog", ["name"])
    op.create_index("ix_product_catalog_code", "product_catalog", ["code"], unique=True)
    op.create_index("ix_product_catalog_animal_type", "product_catalog", ["animal_type"])
    op.create_index("ix_product_catalog_product_type", "product_catalog", ["product_type"])


def downgrade():
    op.drop_index("ix_product_catalog_product_type", table_name="product_catalog")
    op.drop_index("ix_product_catalog_animal_type", table_name="product_catalog")
    op.drop_index("ix_product_catalog_code", table_name="product_catalog")
    op.drop_index("ix_product_catalog_name", table_name="product_catalog")
    op.drop_table("product_catalog")