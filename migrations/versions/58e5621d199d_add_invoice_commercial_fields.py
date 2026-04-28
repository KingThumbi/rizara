"""add invoice commercial fields

Revision ID: 58e5621d199d
Revises: 3e24f21900f2
Create Date: 2026-04-27 19:26:22.348942

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '58e5621d199d'
down_revision = '3e24f21900f2'
branch_labels = None
depends_on = None


def upgrade():
    # ----------------------
    # Add new columns
    # ----------------------
    op.add_column("invoice", sa.Column("contract_document_id", sa.Integer(), nullable=True))
    op.add_column("invoice", sa.Column("currency", sa.String(length=10), nullable=False, server_default="USD"))
    op.add_column("invoice", sa.Column("deposit_paid", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.add_column("invoice", sa.Column("balance", sa.Numeric(14, 2), nullable=False, server_default="0"))

    # ----------------------
    # Foreign key
    # ----------------------
    op.create_foreign_key(
        "fk_invoice_contract_document",
        "invoice",
        "contract_documents",
        ["contract_document_id"],
        ["id"],
    )

    # ----------------------
    # Index
    # ----------------------
    op.create_index(
        "ix_invoice_contract_document_id",
        "invoice",
        ["contract_document_id"],
    )


def downgrade():
    op.drop_index("ix_invoice_contract_document_id", table_name="invoice")
    op.drop_constraint("fk_invoice_contract_document", "invoice", type_="foreignkey")

    op.drop_column("invoice", "balance")
    op.drop_column("invoice", "deposit_paid")
    op.drop_column("invoice", "currency")
    op.drop_column("invoice", "contract_document_id")