"""link contract documents to contracts

Revision ID: fe570bef9df8
Revises: fe995192930f
Create Date: 2026-04-30 21:19:00.271509
"""

from alembic import op
import sqlalchemy as sa


revision = "fe570bef9df8"
down_revision = "fe995192930f"
branch_labels = None
depends_on = None


def upgrade():
    # Link contract documents to buyer for compatibility/reporting.
    # NOTE: actual Buyer table is "buyer", not "buyers".
    op.add_column(
        "contract_documents",
        sa.Column("buyer_id", sa.Integer(), nullable=True),
    )

    # Document workflow status.
    # Use server_default first so existing rows get a safe value.
    op.add_column(
        "contract_documents",
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="uploaded",
        ),
    )

    op.add_column(
        "contract_documents",
        sa.Column("signed_at", sa.DateTime(), nullable=True),
    )

    op.add_column(
        "contract_documents",
        sa.Column("signed_by_name", sa.String(length=255), nullable=True),
    )

    op.add_column(
        "contract_documents",
        sa.Column("signed_by_email", sa.String(length=255), nullable=True),
    )

    op.create_index(
        "ix_contract_documents_buyer_id",
        "contract_documents",
        ["buyer_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_contract_documents_buyer_id",
        "contract_documents",
        "buyer",
        ["buyer_id"],
        ["id"],
    )

    # Remove DB-level default after existing rows are safely populated.
    # Python model default will handle new rows.
    op.alter_column(
        "contract_documents",
        "status",
        server_default=None,
        existing_type=sa.String(length=30),
        existing_nullable=False,
    )


def downgrade():
    op.drop_constraint(
        "fk_contract_documents_buyer_id",
        "contract_documents",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_contract_documents_buyer_id",
        table_name="contract_documents",
    )

    op.drop_column("contract_documents", "signed_by_email")
    op.drop_column("contract_documents", "signed_by_name")
    op.drop_column("contract_documents", "signed_at")
    op.drop_column("contract_documents", "status")
    op.drop_column("contract_documents", "buyer_id")