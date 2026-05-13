"""add kaewa holding pens

Revision ID: 4e6f8a0b2c31
Revises: 3c5d7e9f1a20
Create Date: 2026-05-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "4e6f8a0b2c31"
down_revision = "3c5d7e9f1a20"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "holding_pen",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("office_location", sa.String(length=120), nullable=False),
        sa.Column("animal_type", sa.String(length=20), nullable=False),
        sa.Column("capacity_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_holding_pen_uuid", "holding_pen", ["uuid"], unique=True)
    op.create_index("ix_holding_pen_office_location", "holding_pen", ["office_location"])
    op.create_index("ix_holding_pen_animal_type", "holding_pen", ["animal_type"])
    op.create_index("ix_holding_pen_status", "holding_pen", ["status"])
    op.create_index("ix_holding_pen_created_at", "holding_pen", ["created_at"])

    op.create_table(
        "holding_pen_assignment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("holding_pen_id", sa.Integer(), nullable=False),
        sa.Column("field_livestock_intake_id", sa.Integer(), nullable=True),
        sa.Column("animal_type", sa.String(length=20), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("estimated_total_weight_kg", sa.Numeric(14, 2), nullable=True),
        sa.Column("assigned_at", sa.DateTime(), nullable=False),
        sa.Column("released_at", sa.DateTime(), nullable=True),
        sa.Column("release_reason", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["field_livestock_intake_id"], ["field_livestock_intake.id"]),
        sa.ForeignKeyConstraint(["holding_pen_id"], ["holding_pen.id"]),
    )
    op.create_index("ix_holding_pen_assignment_uuid", "holding_pen_assignment", ["uuid"], unique=True)
    op.create_index("ix_holding_pen_assignment_holding_pen_id", "holding_pen_assignment", ["holding_pen_id"])
    op.create_index(
        "ix_holding_pen_assignment_field_livestock_intake_id",
        "holding_pen_assignment",
        ["field_livestock_intake_id"],
    )
    op.create_index("ix_holding_pen_assignment_animal_type", "holding_pen_assignment", ["animal_type"])
    op.create_index("ix_holding_pen_assignment_assigned_at", "holding_pen_assignment", ["assigned_at"])
    op.create_index("ix_holding_pen_assignment_released_at", "holding_pen_assignment", ["released_at"])
    op.create_index("ix_holding_pen_assignment_release_reason", "holding_pen_assignment", ["release_reason"])
    op.create_index("ix_holding_pen_assignment_status", "holding_pen_assignment", ["status"])
    op.create_index(
        "ix_holding_pen_assignment_created_by_user_id",
        "holding_pen_assignment",
        ["created_by_user_id"],
    )

    op.create_table(
        "holding_pen_activity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("holding_pen_id", sa.Integer(), nullable=False),
        sa.Column("holding_pen_assignment_id", sa.Integer(), nullable=True),
        sa.Column("activity_type", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["holding_pen_assignment_id"], ["holding_pen_assignment.id"]),
        sa.ForeignKeyConstraint(["holding_pen_id"], ["holding_pen.id"]),
    )
    op.create_index("ix_holding_pen_activity_uuid", "holding_pen_activity", ["uuid"], unique=True)
    op.create_index("ix_holding_pen_activity_holding_pen_id", "holding_pen_activity", ["holding_pen_id"])
    op.create_index(
        "ix_holding_pen_activity_holding_pen_assignment_id",
        "holding_pen_activity",
        ["holding_pen_assignment_id"],
    )
    op.create_index("ix_holding_pen_activity_activity_type", "holding_pen_activity", ["activity_type"])
    op.create_index("ix_holding_pen_activity_created_by_user_id", "holding_pen_activity", ["created_by_user_id"])
    op.create_index("ix_holding_pen_activity_created_at", "holding_pen_activity", ["created_at"])


def downgrade():
    op.drop_table("holding_pen_activity")
    op.drop_table("holding_pen_assignment")
    op.drop_table("holding_pen")
