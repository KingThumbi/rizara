"""add grant impact metrics

Revision ID: 0b8c6d4e2f31
Revises: f4a9c2d7e8b1
Create Date: 2026-05-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0b8c6d4e2f31"
down_revision = "f4a9c2d7e8b1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "grant_impact_metric",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("grant_application_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("metric_type", sa.String(length=30), nullable=False),
        sa.Column("unit", sa.String(length=60), nullable=True),
        sa.Column("baseline_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("target_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("current_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("reporting_period_start", sa.Date(), nullable=True),
        sa.Column("reporting_period_end", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["grant_application_id"], ["grant_application.id"]),
    )
    op.create_index("ix_grant_impact_metric_uuid", "grant_impact_metric", ["uuid"], unique=True)
    op.create_index("ix_grant_impact_metric_grant_application_id", "grant_impact_metric", ["grant_application_id"])
    op.create_index("ix_grant_impact_metric_metric_type", "grant_impact_metric", ["metric_type"])
    op.create_index("ix_grant_impact_metric_status", "grant_impact_metric", ["status"])
    op.create_index("ix_grant_impact_metric_created_at", "grant_impact_metric", ["created_at"])


def downgrade():
    op.drop_table("grant_impact_metric")
