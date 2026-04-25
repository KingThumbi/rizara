"""add contract workflow columns only

Revision ID: 8c3d3e5f64f8
Revises: c8ec6b99593d
Create Date: 2026-04-23 13:54:42.130663
"""

from alembic import op
import sqlalchemy as sa


revision = "8c3d3e5f64f8"
down_revision = "c8ec6b99593d"
branch_labels = None
depends_on = None


def upgrade():
    # ---- contracts: additive only, safe for existing data ----
    op.add_column("contracts", sa.Column("submitted_for_review_at", sa.DateTime(), nullable=True))
    op.add_column("contracts", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    op.add_column("contracts", sa.Column("approved_at", sa.DateTime(), nullable=True))
    op.add_column("contracts", sa.Column("signed_at", sa.DateTime(), nullable=True))
    op.add_column("contracts", sa.Column("activated_at", sa.DateTime(), nullable=True))
    op.add_column("contracts", sa.Column("cancelled_at", sa.DateTime(), nullable=True))
    op.add_column("contracts", sa.Column("cancel_reason", sa.Text(), nullable=True))
    op.add_column("contracts", sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True))
    op.add_column("contracts", sa.Column("approved_by_user_id", sa.Integer(), nullable=True))

    op.create_foreign_key(
        "fk_contracts_reviewed_by_user_id",
        "contracts",
        "user",
        ["reviewed_by_user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_contracts_approved_by_user_id",
        "contracts",
        "user",
        ["approved_by_user_id"],
        ["id"],
    )

    # ---- contract documents: brand new additive table ----
    op.create_table(
        "contract_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("document_type", sa.String(length=50), nullable=False, server_default="other"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("stored_filename", sa.String(length=255), nullable=True),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_contract_documents_contract_id",
        "contract_documents",
        ["contract_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_contract_documents_contract_id", table_name="contract_documents")
    op.drop_table("contract_documents")

    op.drop_constraint("fk_contracts_approved_by_user_id", "contracts", type_="foreignkey")
    op.drop_constraint("fk_contracts_reviewed_by_user_id", "contracts", type_="foreignkey")

    op.drop_column("contracts", "approved_by_user_id")
    op.drop_column("contracts", "reviewed_by_user_id")
    op.drop_column("contracts", "cancel_reason")
    op.drop_column("contracts", "cancelled_at")
    op.drop_column("contracts", "activated_at")
    op.drop_column("contracts", "signed_at")
    op.drop_column("contracts", "approved_at")
    op.drop_column("contracts", "reviewed_at")
    op.drop_column("contracts", "submitted_for_review_at")