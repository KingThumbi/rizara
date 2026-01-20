"""add_animal_ops_columns

Revision ID: 0ac2d0a26db2
Revises: faaa0326b1c6
Create Date: 2026-01-19 14:11:11.626931

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0ac2d0a26db2'
down_revision = 'faaa0326b1c6'
branch_labels = None
depends_on = None


def upgrade():
    for table in ("goat", "sheep", "cattle"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(
                sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true())
            )
            batch_op.add_column(sa.Column("aggregated_at", sa.DateTime(), nullable=True))
            batch_op.add_column(sa.Column("aggregated_by_user_id", sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column("live_weight_kg", sa.Float(), nullable=True))
            batch_op.add_column(sa.Column("weight_method", sa.String(length=20), nullable=True))
            batch_op.add_column(sa.Column("purchase_price_per_head", sa.Float(), nullable=True))
            batch_op.add_column(
                sa.Column("purchase_currency", sa.String(length=10), nullable=True, server_default="KES")
            )


def downgrade():
    for table in ("goat", "sheep", "cattle"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_column("purchase_currency")
            batch_op.drop_column("purchase_price_per_head")
            batch_op.drop_column("weight_method")
            batch_op.drop_column("live_weight_kg")
            batch_op.drop_column("aggregated_by_user_id")
            batch_op.drop_column("aggregated_at")
            batch_op.drop_column("is_active")
