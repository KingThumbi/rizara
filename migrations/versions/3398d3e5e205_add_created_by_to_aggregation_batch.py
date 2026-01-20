"""add_created_by_to_aggregation_batch

Revision ID: 3398d3e5e205
Revises: 0ac2d0a26db2
Create Date: 2026-01-19 19:01:49.353218

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3398d3e5e205'
down_revision = '0ac2d0a26db2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("aggregation_batch") as batch_op:
        batch_op.add_column(sa.Column("created_by_user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_aggregation_batch_created_by_user",
            "user",
            ["created_by_user_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("aggregation_batch") as batch_op:
        batch_op.drop_constraint("fk_aggregation_batch_created_by_user", type_="foreignkey")
        batch_op.drop_column("created_by_user_id")
