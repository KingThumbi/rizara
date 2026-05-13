"""add kaewa intake handoff

Revision ID: 3c5d7e9f1a20
Revises: 2d4f6a8b9c10
Create Date: 2026-05-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "3c5d7e9f1a20"
down_revision = "2d4f6a8b9c10"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("field_livestock_intake", sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True))
    op.add_column("field_livestock_intake", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    op.add_column(
        "field_livestock_intake",
        sa.Column("handoff_status", sa.String(length=40), nullable=False, server_default="none"),
    )
    op.add_column("field_livestock_intake", sa.Column("handoff_notes", sa.Text(), nullable=True))
    op.add_column("field_livestock_intake", sa.Column("linked_aggregation_batch_id", sa.Integer(), nullable=True))
    op.add_column("field_livestock_intake", sa.Column("linked_procurement_record_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_field_livestock_intake_reviewed_by_user_id_user",
        "field_livestock_intake",
        "user",
        ["reviewed_by_user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_field_livestock_intake_linked_aggregation_batch_id",
        "field_livestock_intake",
        "aggregation_batch",
        ["linked_aggregation_batch_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_field_livestock_intake_linked_procurement_record_id",
        "field_livestock_intake",
        "procurement_records",
        ["linked_procurement_record_id"],
        ["id"],
    )
    op.create_index("ix_field_livestock_intake_reviewed_by_user_id", "field_livestock_intake", ["reviewed_by_user_id"])
    op.create_index("ix_field_livestock_intake_reviewed_at", "field_livestock_intake", ["reviewed_at"])
    op.create_index("ix_field_livestock_intake_handoff_status", "field_livestock_intake", ["handoff_status"])
    op.create_index(
        "ix_field_livestock_intake_linked_aggregation_batch_id",
        "field_livestock_intake",
        ["linked_aggregation_batch_id"],
    )
    op.create_index(
        "ix_field_livestock_intake_linked_procurement_record_id",
        "field_livestock_intake",
        ["linked_procurement_record_id"],
    )

    op.create_table(
        "field_livestock_intake_activity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("intake_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("from_status", sa.String(length=40), nullable=True),
        sa.Column("to_status", sa.String(length=40), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["intake_id"], ["field_livestock_intake.id"]),
    )
    op.create_index("ix_field_livestock_intake_activity_uuid", "field_livestock_intake_activity", ["uuid"], unique=True)
    op.create_index(
        "ix_field_livestock_intake_activity_intake_id",
        "field_livestock_intake_activity",
        ["intake_id"],
    )
    op.create_index(
        "ix_field_livestock_intake_activity_event_type",
        "field_livestock_intake_activity",
        ["event_type"],
    )
    op.create_index(
        "ix_field_livestock_intake_activity_created_by_user_id",
        "field_livestock_intake_activity",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_field_livestock_intake_activity_created_at",
        "field_livestock_intake_activity",
        ["created_at"],
    )


def downgrade():
    op.drop_table("field_livestock_intake_activity")
    op.drop_index("ix_field_livestock_intake_linked_procurement_record_id", table_name="field_livestock_intake")
    op.drop_index("ix_field_livestock_intake_linked_aggregation_batch_id", table_name="field_livestock_intake")
    op.drop_index("ix_field_livestock_intake_handoff_status", table_name="field_livestock_intake")
    op.drop_index("ix_field_livestock_intake_reviewed_at", table_name="field_livestock_intake")
    op.drop_index("ix_field_livestock_intake_reviewed_by_user_id", table_name="field_livestock_intake")
    op.drop_constraint(
        "fk_field_livestock_intake_linked_procurement_record_id",
        "field_livestock_intake",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_field_livestock_intake_linked_aggregation_batch_id",
        "field_livestock_intake",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_field_livestock_intake_reviewed_by_user_id_user",
        "field_livestock_intake",
        type_="foreignkey",
    )
    op.drop_column("field_livestock_intake", "linked_procurement_record_id")
    op.drop_column("field_livestock_intake", "linked_aggregation_batch_id")
    op.drop_column("field_livestock_intake", "handoff_notes")
    op.drop_column("field_livestock_intake", "handoff_status")
    op.drop_column("field_livestock_intake", "reviewed_at")
    op.drop_column("field_livestock_intake", "reviewed_by_user_id")
