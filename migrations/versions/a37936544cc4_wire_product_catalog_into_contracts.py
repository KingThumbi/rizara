"""wire product catalog into contracts

Revision ID: a37936544cc4
Revises: f051016f54b9
Create Date: 2026-05-03 21:13:53.600187
"""

from alembic import op
import sqlalchemy as sa


revision = "a37936544cc4"
down_revision = "f051016f54b9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "contracts",
        sa.Column("product_catalog_id", sa.Integer(), nullable=True),
    )

    op.create_foreign_key(
        "fk_contracts_product_catalog",
        "contracts",
        "product_catalog",
        ["product_catalog_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint(
        "fk_contracts_product_catalog",
        "contracts",
        type_="foreignkey",
    )

    op.drop_column("contracts", "product_catalog_id")