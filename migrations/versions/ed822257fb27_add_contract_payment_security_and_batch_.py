"""add contract payment security and batch release fields

Revision ID: ed822257fb27
Revises: 750646426195
Create Date: 2026-04-21 22:42:16.303068
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ed822257fb27"
down_revision = "750646426195"
branch_labels = None
depends_on = None


def upgrade():
    # ---------------------------------------------------------
    # contracts: payment security / release logic
    # ---------------------------------------------------------
    op.add_column(
        "contracts",
        sa.Column(
            "payment_security_type",
            sa.String(length=30),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "contracts",
        sa.Column(
            "prepayment_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "contracts",
        sa.Column(
            "lc_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "contracts",
        sa.Column("lc_number", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "contracts",
        sa.Column("lc_issuing_bank", sa.String(length=150), nullable=True),
    )
    op.add_column(
        "contracts",
        sa.Column(
            "lc_status",
            sa.String(length=30),
            nullable=True,
        ),
    )
    op.add_column(
        "contracts",
        sa.Column(
            "processing_release_mode",
            sa.String(length=30),
            nullable=False,
            server_default="manual_approval",
        ),
    )

    op.create_index(
        "ix_contracts_payment_security",
        "contracts",
        ["payment_security_type"],
    )
    op.create_index(
        "ix_contracts_lc_status",
        "contracts",
        ["lc_status"],
    )
    op.create_index(
        "ix_contracts_release_mode",
        "contracts",
        ["processing_release_mode"],
    )

    # ---------------------------------------------------------
    # processing_batches: why batch was released
    # ---------------------------------------------------------
    op.add_column(
        "processing_batches",
        sa.Column(
            "authorization_basis",
            sa.String(length=30),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_pb_auth_basis",
        "processing_batches",
        ["authorization_basis"],
    )

    # Optional cleanup of server defaults for future inserts handled by app
    op.alter_column("contracts", "payment_security_type", server_default=None)
    op.alter_column("contracts", "prepayment_required", server_default=None)
    op.alter_column("contracts", "lc_required", server_default=None)
    op.alter_column("contracts", "processing_release_mode", server_default=None)


def downgrade():
    op.drop_index("ix_pb_auth_basis", table_name="processing_batches")
    op.drop_column("processing_batches", "authorization_basis")

    op.drop_index("ix_contracts_release_mode", table_name="contracts")
    op.drop_index("ix_contracts_lc_status", table_name="contracts")
    op.drop_index("ix_contracts_payment_security", table_name="contracts")

    op.drop_column("contracts", "processing_release_mode")
    op.drop_column("contracts", "lc_status")
    op.drop_column("contracts", "lc_issuing_bank")
    op.drop_column("contracts", "lc_number")
    op.drop_column("contracts", "lc_required")
    op.drop_column("contracts", "prepayment_required")
    op.drop_column("contracts", "payment_security_type")