"""Enforce single aggregation batch per goat

Revision ID: enforce_single_aggregation
Revises: 8c8a1d243e14
Create Date: 2026-01-09 22:45:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'enforce_single_aggregation'
down_revision = '8c8a1d243e14'
branch_labels = None
depends_on = None


def upgrade():
    # Step 1: Add aggregation_batch_id column to goat table
    op.add_column('goat', sa.Column('aggregation_batch_id', sa.Integer(), nullable=True))

    # Step 2: Create foreign key constraint to aggregation_batch table
    op.create_foreign_key(
        'fk_goat_aggregation_batch',   # constraint name
        'goat',                        # source table
        'aggregation_batch',           # target table
        ['aggregation_batch_id'],      # local columns
        ['id'],                        # remote columns
        ondelete='SET NULL'            # optional, matches your model
    )


def downgrade():
    # Step 1: Drop foreign key constraint
    op.drop_constraint('fk_goat_aggregation_batch', 'goat', type_='foreignkey')

    # Step 2: Drop aggregation_batch_id column
    op.drop_column('goat', 'aggregation_batch_id')
