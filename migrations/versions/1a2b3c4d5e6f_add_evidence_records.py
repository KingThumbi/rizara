"""add evidence records

Revision ID: 1a2b3c4d5e6f
Revises: 9d1e5f7a2c44
Create Date: 2026-05-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "1a2b3c4d5e6f"
down_revision = "9d1e5f7a2c44"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "evidence_record",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("linked_model_type", sa.String(length=80), nullable=False),
        sa.Column("linked_model_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("evidence_type", sa.String(length=40), nullable=False),
        sa.Column("file_path", sa.String(length=255), nullable=True),
        sa.Column("external_url", sa.String(length=500), nullable=True),
        sa.Column("county", sa.String(length=100), nullable=True),
        sa.Column("captured_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_evidence_record_uuid", "evidence_record", ["uuid"], unique=True)
    op.create_index("ix_evidence_record_linked_model_type", "evidence_record", ["linked_model_type"])
    op.create_index("ix_evidence_record_linked_model_id", "evidence_record", ["linked_model_id"])
    op.create_index("ix_evidence_record_evidence_type", "evidence_record", ["evidence_type"])
    op.create_index("ix_evidence_record_county", "evidence_record", ["county"])
    op.create_index("ix_evidence_record_captured_on", "evidence_record", ["captured_on"])
    op.create_index("ix_evidence_record_created_at", "evidence_record", ["created_at"])


def downgrade():
    op.drop_table("evidence_record")
