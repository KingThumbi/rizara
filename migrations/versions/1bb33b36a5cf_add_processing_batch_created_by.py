"""add_processing_batch_created_by

Revision ID: 1bb33b36a5cf
Revises: 825e3c9f6bb0
Create Date: 2026-01-19 20:06:21.969215

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1bb33b36a5cf'
down_revision = '825e3c9f6bb0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("processing_batch", schema=None) as batch_op:
        batch_op.add_column(sa.Column("created_by_user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_processing_batch_created_by_user",
            "user",
            ["created_by_user_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("processing_batch", schema=None) as batch_op:
        batch_op.drop_constraint("fk_processing_batch_created_by_user", type_="foreignkey")
        batch_op.drop_column("created_by_user_id")

