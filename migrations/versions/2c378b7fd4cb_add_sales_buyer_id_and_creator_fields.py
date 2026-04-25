"""add sales buyer_id and creator fields

Revision ID: 2c378b7fd4cb
Revises: 0326cffb68cf
Create Date: 2026-04-23 18:00:24.199427

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2c378b7fd4cb'
down_revision = '0326cffb68cf'
branch_labels = None
depends_on = None


def upgrade():
    # ---- sales: add new fields (non-destructive) ----
    op.add_column("sales", sa.Column("buyer_id", sa.Integer(), nullable=True))
    op.add_column("sales", sa.Column("created_by_user_id", sa.Integer(), nullable=True))

    op.create_foreign_key(
        "fk_sales_buyer_id",
        "sales",
        "buyer",
        ["buyer_id"],
        ["id"],
    )

    op.create_foreign_key(
        "fk_sales_created_by_user_id",
        "sales",
        "user",
        ["created_by_user_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint("fk_sales_created_by_user_id", "sales", type_="foreignkey")
    op.drop_constraint("fk_sales_buyer_id", "sales", type_="foreignkey")

    op.drop_column("sales", "created_by_user_id")
    op.drop_column("sales", "buyer_id")