"""link invoices to sale contract and commercial batch

Revision ID: 34f351b3f74d
Revises: 0a03e2430cd5
Create Date: 2026-04-26 18:13:28.447319
"""

from alembic import op
import sqlalchemy as sa


revision = "34f351b3f74d"
down_revision = "0a03e2430cd5"
branch_labels = None
depends_on = None


def upgrade():
    # Add modern invoice links
    op.add_column("invoice", sa.Column("sale_id", sa.Integer(), nullable=True))
    op.add_column("invoice", sa.Column("contract_id", sa.Integer(), nullable=True))
    op.add_column("invoice", sa.Column("commercial_processing_batch_id", sa.Integer(), nullable=True))

    # Add audit timestamp safely with server default for existing rows
    op.add_column(
        "invoice",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Allow legacy processing_batch_sale_id to be nullable
    op.alter_column(
        "invoice",
        "processing_batch_sale_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    # Add indexes
    op.create_index("ix_invoice_sale_id", "invoice", ["sale_id"], unique=False)
    op.create_index("ix_invoice_contract_id", "invoice", ["contract_id"], unique=False)
    op.create_index(
        "ix_invoice_commercial_processing_batch_id",
        "invoice",
        ["commercial_processing_batch_id"],
        unique=False,
    )

    # Add foreign keys
    op.create_foreign_key(
        "fk_invoice_sale_id_sales",
        "invoice",
        "sales",
        ["sale_id"],
        ["id"],
    )

    op.create_foreign_key(
        "fk_invoice_contract_id_contracts",
        "invoice",
        "contracts",
        ["contract_id"],
        ["id"],
    )


def downgrade():
    # Drop foreign keys
    op.drop_constraint(
        "fk_invoice_commercial_processing_batch_id",
        "invoice",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_invoice_contract_id_contracts",
        "invoice",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_invoice_sale_id_sales",
        "invoice",
        type_="foreignkey",
    )

    # Drop indexes
    op.drop_index("ix_invoice_commercial_processing_batch_id", table_name="invoice")
    op.drop_index("ix_invoice_contract_id", table_name="invoice")
    op.drop_index("ix_invoice_sale_id", table_name="invoice")

    # Restore old nullable rule
    op.alter_column(
        "invoice",
        "processing_batch_sale_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # Drop added columns
    op.drop_column("invoice", "updated_at")
    op.drop_column("invoice", "commercial_processing_batch_id")
    op.drop_column("invoice", "contract_id")
    op.drop_column("invoice", "sale_id")