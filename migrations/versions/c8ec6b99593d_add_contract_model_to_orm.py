"""add contract model to ORM

Revision ID: c8ec6b99593d
Revises: ed822257fb27
Create Date: 2026-04-21 22:56:39.748577
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c8ec6b99593d"
down_revision = "ed822257fb27"
branch_labels = None
depends_on = None


def upgrade():
    # 1) Add new ORM-aligned columns as nullable first
    op.add_column("contracts", sa.Column("buyer_id", sa.Integer(), nullable=True))
    op.add_column("contracts", sa.Column("created_by_user_id", sa.Integer(), nullable=True))

    # 2) Backfill buyer_id from existing customer_id
    # IMPORTANT:
    # This assumes contracts.customer_id currently stores buyer.id values.
    # If that is not true in your data, stop here and verify before running.
    op.execute(
        """
        UPDATE contracts
        SET buyer_id = customer_id
        WHERE buyer_id IS NULL
        """
    )

    # 3) Backfill created_by_user_id from existing created_by
    op.execute(
        """
        UPDATE contracts
        SET created_by_user_id = created_by
        WHERE created_by_user_id IS NULL
        """
    )

    # 4) Add index + foreign keys
    op.create_index("ix_contracts_buyer_id", "contracts", ["buyer_id"], unique=False)
    op.create_index("ix_contracts_created_by_user_id", "contracts", ["created_by_user_id"], unique=False)

    op.create_foreign_key(
        "fk_contracts_buyer_id",
        "contracts",
        "buyer",
        ["buyer_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_contracts_created_by_user_id",
        "contracts",
        "user",
        ["created_by_user_id"],
        ["id"],
    )

    # 5) Make buyer_id non-nullable after backfill
    op.alter_column("contracts", "buyer_id", nullable=False)

    # 6) Drop old columns only after successful backfill
    op.drop_index("ix_contracts_customer", table_name="contracts")
    op.drop_column("contracts", "customer_id")
    op.drop_column("contracts", "created_by")


def downgrade():
    # 1) Re-add old columns
    op.add_column("contracts", sa.Column("created_by", sa.Integer(), nullable=True))
    op.add_column("contracts", sa.Column("customer_id", sa.Integer(), nullable=True))

    # 2) Backfill from new columns
    op.execute(
        """
        UPDATE contracts
        SET customer_id = buyer_id
        WHERE customer_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE contracts
        SET created_by = created_by_user_id
        WHERE created_by IS NULL
        """
    )

    # 3) Restore old index
    op.create_index("ix_contracts_customer", "contracts", ["customer_id"], unique=False)

    # 4) Make customer_id non-nullable again
    op.alter_column("contracts", "customer_id", nullable=False)

    # 5) Drop new foreign keys and indexes
    op.drop_constraint("fk_contracts_created_by_user_id", "contracts", type_="foreignkey")
    op.drop_constraint("fk_contracts_buyer_id", "contracts", type_="foreignkey")
    op.drop_index("ix_contracts_created_by_user_id", table_name="contracts")
    op.drop_index("ix_contracts_buyer_id", table_name="contracts")

    # 6) Drop new columns
    op.drop_column("contracts", "created_by_user_id")
    op.drop_column("contracts", "buyer_id")