"""add market purchase tables

Revision ID: 3af2009e4f8a
Revises: c29160e8b55b
Create Date: 2026-04-17 22:24:48.997876

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3af2009e4f8a"
down_revision = "c29160e8b55b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "market_purchase",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("aggregation_batch_id", sa.Integer(), nullable=False),
        sa.Column("animal_type", sa.String(length=20), nullable=False),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("market_name", sa.String(length=120), nullable=False),
        sa.Column("vendor_name", sa.String(length=160), nullable=True),
        sa.Column("broker_name", sa.String(length=160), nullable=True),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "animal_type in ('goat','sheep','cattle')",
            name="ck_market_purchase_animal_type",
        ),
        sa.CheckConstraint(
            "status in ('draft','confirmed','received','cancelled')",
            name="ck_market_purchase_status",
        ),
        sa.ForeignKeyConstraint(
            ["aggregation_batch_id"],
            ["aggregation_batch.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_market_purchase_aggregation_batch_id",
        "market_purchase",
        ["aggregation_batch_id"],
        unique=False,
    )
    op.create_index(
        "ix_market_purchase_status",
        "market_purchase",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_market_purchase_batch_animal_status",
        "market_purchase",
        ["aggregation_batch_id", "animal_type", "status"],
        unique=False,
    )

    op.create_table(
        "market_purchase_line",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_purchase_id", sa.Integer(), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("unit_price_kes", sa.Float(), nullable=False),
        sa.Column("total_price_kes", sa.Float(), nullable=False),
        sa.Column("estimated_live_weight_per_head_kg", sa.Float(), nullable=True),
        sa.Column("estimated_carcass_weight_per_head_kg", sa.Float(), nullable=True),
        sa.Column("avg_age_months", sa.Integer(), nullable=True),
        sa.Column("weight_method", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "qty > 0",
            name="ck_market_purchase_line_qty_positive",
        ),
        sa.CheckConstraint(
            "unit_price_kes >= 0",
            name="ck_market_purchase_line_unit_price_non_negative",
        ),
        sa.CheckConstraint(
            "total_price_kes >= 0",
            name="ck_market_purchase_line_total_non_negative",
        ),
        sa.CheckConstraint(
            "(estimated_live_weight_per_head_kg is null) or (estimated_live_weight_per_head_kg >= 0)",
            name="ck_market_purchase_line_live_weight_non_negative",
        ),
        sa.CheckConstraint(
            "(estimated_carcass_weight_per_head_kg is null) or (estimated_carcass_weight_per_head_kg >= 0)",
            name="ck_market_purchase_line_carcass_weight_non_negative",
        ),
        sa.CheckConstraint(
            "(avg_age_months is null) or (avg_age_months >= 0)",
            name="ck_market_purchase_line_avg_age_non_negative",
        ),
        sa.CheckConstraint(
            "(weight_method is null) or (weight_method in ('estimated','scale','tape','other'))",
            name="ck_market_purchase_line_weight_method",
        ),
        sa.ForeignKeyConstraint(
            ["market_purchase_id"],
            ["market_purchase.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_market_purchase_line_market_purchase_id",
        "market_purchase_line",
        ["market_purchase_id"],
        unique=False,
    )

    op.create_table(
        "market_purchase_expense",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("aggregation_batch_id", sa.Integer(), nullable=False),
        sa.Column("market_purchase_id", sa.Integer(), nullable=False),
        sa.Column("expense_type", sa.String(length=40), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("incurred_date", sa.Date(), nullable=False),
        sa.Column("paid_to", sa.String(length=160), nullable=True),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "amount >= 0",
            name="ck_market_purchase_expense_amount_non_negative",
        ),
        sa.CheckConstraint(
            "expense_type in ('transport','documentation','broker','accommodation','meals','miscellaneous','loading','offloading','labour','permit','fuel','other')",
            name="ck_market_purchase_expense_type",
        ),
        sa.ForeignKeyConstraint(
            ["aggregation_batch_id"],
            ["aggregation_batch.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["market_purchase_id"],
            ["market_purchase.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_market_purchase_expense_aggregation_batch_id",
        "market_purchase_expense",
        ["aggregation_batch_id"],
        unique=False,
    )
    op.create_index(
        "ix_market_purchase_expense_market_purchase_id",
        "market_purchase_expense",
        ["market_purchase_id"],
        unique=False,
    )
    op.create_index(
        "ix_market_purchase_expense_expense_type",
        "market_purchase_expense",
        ["expense_type"],
        unique=False,
    )
    op.create_index(
        "ix_market_purchase_expense_batch_purchase_type",
        "market_purchase_expense",
        ["aggregation_batch_id", "market_purchase_id", "expense_type"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_market_purchase_expense_batch_purchase_type",
        table_name="market_purchase_expense",
    )
    op.drop_index(
        "ix_market_purchase_expense_expense_type",
        table_name="market_purchase_expense",
    )
    op.drop_index(
        "ix_market_purchase_expense_market_purchase_id",
        table_name="market_purchase_expense",
    )
    op.drop_index(
        "ix_market_purchase_expense_aggregation_batch_id",
        table_name="market_purchase_expense",
    )
    op.drop_table("market_purchase_expense")

    op.drop_index(
        "ix_market_purchase_line_market_purchase_id",
        table_name="market_purchase_line",
    )
    op.drop_table("market_purchase_line")

    op.drop_index(
        "ix_market_purchase_batch_animal_status",
        table_name="market_purchase",
    )
    op.drop_index(
        "ix_market_purchase_status",
        table_name="market_purchase",
    )
    op.drop_index(
        "ix_market_purchase_aggregation_batch_id",
        table_name="market_purchase",
    )
    op.drop_table("market_purchase")