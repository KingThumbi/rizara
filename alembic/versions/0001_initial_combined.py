"""Initial combined migration

Revision ID: 0001_initial_combined
Revises: 
Create Date: 2026-01-11 22:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '0001_initial_combined'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Upgrade schema: create tables and columns."""
    
    # -----------------------
    # aggregation_batch table
    # -----------------------
    op.create_table(
        'aggregation_batch',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # -----------------------
    # processing_batch table
    # -----------------------
    op.create_table(
        'processing_batch',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # -----------------------
    # goat table
    # -----------------------
    op.create_table(
        'goat',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('aggregation_batch_id', sa.Integer(), nullable=True),
    )

    # Foreign key from goat to aggregation_batch
    op.create_foreign_key(
        'fk_goat_aggregation_batch',
        'goat',
        'aggregation_batch',
        ['aggregation_batch_id'],
        ['id'],
        ondelete='SET NULL'
    )

def downgrade() -> None:
    """Downgrade schema: drop tables and constraints."""
    op.drop_constraint('fk_goat_aggregation_batch', 'goat', type_='foreignkey')
    op.drop_table('goat')
    op.drop_table('processing_batch')
    op.drop_table('aggregation_batch')
