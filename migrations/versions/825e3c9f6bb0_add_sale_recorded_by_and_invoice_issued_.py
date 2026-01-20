"""add_sale_recorded_by_and_invoice_issued_by

Revision ID: 825e3c9f6bb0
Revises: 3398d3e5e205
Create Date: 2026-01-19 19:55:43.067866

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '825e3c9f6bb0'
down_revision = '3398d3e5e205'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("processing_batch_sale") as batch_op:
        batch_op.add_column(sa.Column("recorded_by_user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_processing_batch_sale_recorded_by_user",
            "user",
            ["recorded_by_user_id"],
            ["id"],
        )

    with op.batch_alter_table("invoice") as batch_op:
        batch_op.add_column(sa.Column("issued_by_user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_invoice_issued_by_user",
            "user",
            ["issued_by_user_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("invoice") as batch_op:
        batch_op.drop_constraint("fk_invoice_issued_by_user", type_="foreignkey")
        batch_op.drop_column("issued_by_user_id")

    with op.batch_alter_table("processing_batch_sale") as batch_op:
        batch_op.drop_constraint("fk_processing_batch_sale_recorded_by_user", type_="foreignkey")
        batch_op.drop_column("recorded_by_user_id")