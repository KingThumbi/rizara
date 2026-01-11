"""real initial schema

Revision ID: 8c399bced0b0
Revises: 
Create Date: 2026-01-11 22:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as psql

# revision identifiers, used by Alembic.
revision = '8c399bced0b0'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------
    # User table
    # -------------------------------
    op.create_table(
        'user',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('email', sa.String(120), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('is_admin', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now())
    )

    # -------------------------------
    # Farmer table
    # -------------------------------
    op.create_table(
        'farmer',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('phone', sa.String(20), unique=True, nullable=False),
        sa.Column('county', sa.String(100), nullable=False),
        sa.Column('ward', sa.String(100), nullable=False),
        sa.Column('village', sa.String(120)),
        sa.Column('latitude', sa.Float),
        sa.Column('longitude', sa.Float),
        sa.Column('location_notes', sa.String(255)),
        sa.Column('onboarded_at', sa.DateTime, server_default=sa.func.now())
    )

    # -------------------------------
    # Aggregation Batch table
    # -------------------------------
    op.create_table(
        'aggregation_batch',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('site_name', sa.String(120), nullable=False),
        sa.Column('date_received', sa.Date, server_default=sa.func.current_date()),
        sa.Column('is_locked', sa.Boolean, default=False),
        sa.Column('locked_at', sa.DateTime),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now())
    )

    # -------------------------------
    # Goat table
    # -------------------------------
    op.create_table(
        'goat',
        sa.Column('id', psql.UUID(as_uuid=True), primary_key=True),
        sa.Column('farmer_tag', sa.String(64), nullable=False),
        sa.Column('rizara_id', sa.String(64), unique=True, nullable=False),
        sa.Column('sex', sa.String(10)),
        sa.Column('breed', sa.String(50)),
        sa.Column('estimated_dob', sa.Date),
        sa.Column('status', sa.String(30), nullable=False, server_default='on_farm'),
        sa.Column('farmer_id', sa.Integer, sa.ForeignKey('farmer.id'), nullable=False),
        sa.Column('aggregation_batch_id', sa.Integer, sa.ForeignKey('aggregation_batch.id')),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now())
    )

    # -------------------------------
    # Processing Batch table
    # -------------------------------
    op.create_table(
        'processing_batch',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('facility', sa.String(120), nullable=False),
        sa.Column('slaughter_date', sa.Date),
        sa.Column('halal_cert_ref', sa.String(120)),
        sa.Column('is_locked', sa.Boolean, default=False),
        sa.Column('locked_at', sa.DateTime),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now())
    )

    # -------------------------------
    # Association table for processing_goats
    # -------------------------------
    op.create_table(
        'processing_goats',
        sa.Column('processing_batch_id', sa.Integer, sa.ForeignKey('processing_batch.id'), primary_key=True),
        sa.Column('goat_id', psql.UUID(as_uuid=True), sa.ForeignKey('goat.id'), primary_key=True)
    )

    # -------------------------------
    # Traceability Records table
    # -------------------------------
    op.create_table(
        'traceability_record',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('goat_id', psql.UUID(as_uuid=True), sa.ForeignKey('goat.id'), nullable=False),
        sa.Column('qr_code_data', sa.Text, nullable=False),
        sa.Column('public_url', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now())
    )


def downgrade() -> None:
    op.drop_table('traceability_record')
    op.drop_table('processing_goats')
    op.drop_table('processing_batch')
    op.drop_table('goat')
    op.drop_table('aggregation_batch')
    op.drop_table('farmer')
    op.drop_table('user')
