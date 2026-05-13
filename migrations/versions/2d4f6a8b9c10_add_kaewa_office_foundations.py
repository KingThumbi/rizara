"""add kaewa office foundations

Revision ID: 2d4f6a8b9c10
Revises: 1a2b3c4d5e6f
Create Date: 2026-05-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "2d4f6a8b9c10"
down_revision = "1a2b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stakeholder",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=False),
        sa.Column("email", sa.String(length=120), nullable=True),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("county", sa.String(length=100), nullable=True),
        sa.Column("sub_county", sa.String(length=100), nullable=True),
        sa.Column("ward", sa.String(length=100), nullable=True),
        sa.Column("village", sa.String(length=120), nullable=True),
        sa.Column("national_id", sa.String(length=60), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
    )
    op.create_index("ix_stakeholder_uuid", "stakeholder", ["uuid"], unique=True)
    op.create_index("ix_stakeholder_phone", "stakeholder", ["phone"])
    op.create_index("ix_stakeholder_category", "stakeholder", ["category"])
    op.create_index("ix_stakeholder_county", "stakeholder", ["county"])
    op.create_index("ix_stakeholder_sub_county", "stakeholder", ["sub_county"])
    op.create_index("ix_stakeholder_ward", "stakeholder", ["ward"])
    op.create_index("ix_stakeholder_status", "stakeholder", ["status"])
    op.create_index("ix_stakeholder_created_by_user_id", "stakeholder", ["created_by_user_id"])
    op.create_index("ix_stakeholder_created_at", "stakeholder", ["created_at"])

    op.create_table(
        "stakeholder_activity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("stakeholder_id", sa.Integer(), nullable=False),
        sa.Column("activity_type", sa.String(length=40), nullable=False),
        sa.Column("subject", sa.String(length=180), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("activity_date", sa.Date(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["stakeholder_id"], ["stakeholder.id"]),
    )
    op.create_index("ix_stakeholder_activity_uuid", "stakeholder_activity", ["uuid"], unique=True)
    op.create_index("ix_stakeholder_activity_stakeholder_id", "stakeholder_activity", ["stakeholder_id"])
    op.create_index("ix_stakeholder_activity_activity_type", "stakeholder_activity", ["activity_type"])
    op.create_index("ix_stakeholder_activity_activity_date", "stakeholder_activity", ["activity_date"])
    op.create_index("ix_stakeholder_activity_created_by_user_id", "stakeholder_activity", ["created_by_user_id"])
    op.create_index("ix_stakeholder_activity_created_at", "stakeholder_activity", ["created_at"])

    op.create_table(
        "stakeholder_document",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("stakeholder_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("document_type", sa.String(length=60), nullable=False),
        sa.Column("file_path", sa.String(length=255), nullable=True),
        sa.Column("external_url", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["stakeholder_id"], ["stakeholder.id"]),
    )
    op.create_index("ix_stakeholder_document_uuid", "stakeholder_document", ["uuid"], unique=True)
    op.create_index("ix_stakeholder_document_stakeholder_id", "stakeholder_document", ["stakeholder_id"])
    op.create_index("ix_stakeholder_document_document_type", "stakeholder_document", ["document_type"])
    op.create_index("ix_stakeholder_document_created_by_user_id", "stakeholder_document", ["created_by_user_id"])
    op.create_index("ix_stakeholder_document_created_at", "stakeholder_document", ["created_at"])

    op.create_table(
        "field_livestock_intake",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("stakeholder_id", sa.Integer(), nullable=True),
        sa.Column("office_location", sa.String(length=120), nullable=False),
        sa.Column("animal_type", sa.String(length=20), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("estimated_total_weight_kg", sa.Numeric(14, 2), nullable=True),
        sa.Column("source_location", sa.String(length=180), nullable=True),
        sa.Column("intake_status", sa.String(length=40), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["stakeholder_id"], ["stakeholder.id"]),
    )
    op.create_index("ix_field_livestock_intake_uuid", "field_livestock_intake", ["uuid"], unique=True)
    op.create_index("ix_field_livestock_intake_stakeholder_id", "field_livestock_intake", ["stakeholder_id"])
    op.create_index("ix_field_livestock_intake_office_location", "field_livestock_intake", ["office_location"])
    op.create_index("ix_field_livestock_intake_animal_type", "field_livestock_intake", ["animal_type"])
    op.create_index("ix_field_livestock_intake_source_location", "field_livestock_intake", ["source_location"])
    op.create_index("ix_field_livestock_intake_intake_status", "field_livestock_intake", ["intake_status"])
    op.create_index("ix_field_livestock_intake_created_by_user_id", "field_livestock_intake", ["created_by_user_id"])
    op.create_index("ix_field_livestock_intake_created_at", "field_livestock_intake", ["created_at"])


def downgrade():
    op.drop_table("field_livestock_intake")
    op.drop_table("stakeholder_document")
    op.drop_table("stakeholder_activity")
    op.drop_table("stakeholder")
