"""add impact snapshots

Revision ID: 9d1e5f7a2c44
Revises: 0b8c6d4e2f31
Create Date: 2026-05-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "9d1e5f7a2c44"
down_revision = "0b8c6d4e2f31"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("grant_impact_metric", sa.Column("metric_code", sa.String(length=80), nullable=True))
    op.create_index("ix_grant_impact_metric_metric_code", "grant_impact_metric", ["metric_code"])

    op.create_table(
        "impact_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("metric_code", sa.String(length=80), nullable=False),
        sa.Column("metric_name", sa.String(length=180), nullable=False),
        sa.Column("metric_category", sa.String(length=60), nullable=False),
        sa.Column("metric_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("metric_unit", sa.String(length=60), nullable=True),
        sa.Column("county", sa.String(length=100), nullable=True),
        sa.Column("animal_type", sa.String(length=20), nullable=True),
        sa.Column("source_module", sa.String(length=80), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_impact_snapshot_uuid", "impact_snapshot", ["uuid"], unique=True)
    op.create_index("ix_impact_snapshot_snapshot_date", "impact_snapshot", ["snapshot_date"])
    op.create_index("ix_impact_snapshot_metric_code", "impact_snapshot", ["metric_code"])
    op.create_index("ix_impact_snapshot_metric_category", "impact_snapshot", ["metric_category"])
    op.create_index("ix_impact_snapshot_county", "impact_snapshot", ["county"])
    op.create_index("ix_impact_snapshot_animal_type", "impact_snapshot", ["animal_type"])
    op.create_index("ix_impact_snapshot_source_module", "impact_snapshot", ["source_module"])
    op.create_index("ix_impact_snapshot_created_at", "impact_snapshot", ["created_at"])


def downgrade():
    op.drop_table("impact_snapshot")
    op.drop_index("ix_grant_impact_metric_metric_code", table_name="grant_impact_metric")
    op.drop_column("grant_impact_metric", "metric_code")
