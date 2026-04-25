"""add pipeline case tables

Revision ID: ec6e3639afa1
Revises: 2c378b7fd4cb
Create Date: 2026-04-23 23:16:47.884398
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "ec6e3639afa1"
down_revision = "2c378b7fd4cb"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pipeline_case",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_number", sa.String(50), nullable=False),

        sa.Column("buyer_id", sa.Integer(), nullable=True),
        sa.Column("contract_id", sa.Integer(), nullable=True),

        # Keep this as plain integer for now.
        # Do not add FK until commercial_processing_batches exists in DB.
        sa.Column("commercial_processing_batch_id", sa.Integer(), nullable=True),

        sa.Column("sale_id", sa.Integer(), nullable=True),
        sa.Column("invoice_id", sa.Integer(), nullable=True),

        sa.Column("current_stage", sa.String(30), nullable=False, server_default="sourcing"),
        sa.Column("current_status", sa.String(40), nullable=False, server_default="draft"),
        sa.Column("authorization_status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("payment_status", sa.String(30), nullable=False, server_default="none"),
        sa.Column("delivery_status", sa.String(30), nullable=False, server_default="not_started"),
        sa.Column("health_status", sa.String(20), nullable=False, server_default="green"),
        sa.Column("next_action", sa.String(50), nullable=False, server_default="capture_source"),

        sa.Column("next_action_label", sa.String(255), nullable=True),
        sa.Column("blocking_reason", sa.Text(), nullable=True),

        sa.Column("output_qty", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("sold_qty", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("invoiced_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("paid_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("outstanding_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),

        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),

        sa.ForeignKeyConstraint(["buyer_id"], ["buyer.id"], name="fk_pipeline_case_buyer_id"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], name="fk_pipeline_case_contract_id"),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], name="fk_pipeline_case_sale_id"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoice.id"], name="fk_pipeline_case_invoice_id"),
        sa.UniqueConstraint("case_number", name="uq_pipeline_case_case_number"),
    )

    op.create_index("ix_pipeline_case_case_number", "pipeline_case", ["case_number"], unique=True)
    op.create_index("ix_pipeline_case_buyer_id", "pipeline_case", ["buyer_id"])
    op.create_index("ix_pipeline_case_contract_id", "pipeline_case", ["contract_id"])
    op.create_index("ix_pipeline_case_commercial_processing_batch_id", "pipeline_case", ["commercial_processing_batch_id"])
    op.create_index("ix_pipeline_case_sale_id", "pipeline_case", ["sale_id"])
    op.create_index("ix_pipeline_case_invoice_id", "pipeline_case", ["invoice_id"])
    op.create_index("ix_pipeline_case_current_stage", "pipeline_case", ["current_stage"])
    op.create_index("ix_pipeline_case_current_status", "pipeline_case", ["current_status"])
    op.create_index("ix_pipeline_case_authorization_status", "pipeline_case", ["authorization_status"])
    op.create_index("ix_pipeline_case_payment_status", "pipeline_case", ["payment_status"])
    op.create_index("ix_pipeline_case_delivery_status", "pipeline_case", ["delivery_status"])
    op.create_index("ix_pipeline_case_health_status", "pipeline_case", ["health_status"])

    op.create_table(
        "pipeline_delivery",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pipeline_case_id", sa.Integer(), nullable=False),
        sa.Column("sale_id", sa.Integer(), nullable=True),
        sa.Column("delivery_number", sa.String(50), nullable=True),
        sa.Column("destination", sa.String(200), nullable=True),
        sa.Column("shipping_mode", sa.String(50), nullable=True),
        sa.Column("quantity_kg", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("dispatch_date", sa.Date(), nullable=True),
        sa.Column("delivery_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="planned"),
        sa.Column("shipping_docs_uploaded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("proof_of_delivery_uploaded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["pipeline_case_id"],
            ["pipeline_case.id"],
            name="fk_pipeline_delivery_pipeline_case_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], name="fk_pipeline_delivery_sale_id"),
    )

    op.create_index("ix_pipeline_delivery_pipeline_case_id", "pipeline_delivery", ["pipeline_case_id"])
    op.create_index("ix_pipeline_delivery_sale_id", "pipeline_delivery", ["sale_id"])
    op.create_index("ix_pipeline_delivery_delivery_number", "pipeline_delivery", ["delivery_number"])
    op.create_index("ix_pipeline_delivery_status", "pipeline_delivery", ["status"])

    op.create_table(
        "pipeline_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pipeline_case_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("event_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["pipeline_case_id"],
            ["pipeline_case.id"],
            name="fk_pipeline_event_pipeline_case_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["user.id"], name="fk_pipeline_event_actor_user_id"),
    )

    op.create_index("ix_pipeline_event_pipeline_case_id", "pipeline_event", ["pipeline_case_id"])
    op.create_index("ix_pipeline_event_event_type", "pipeline_event", ["event_type"])
    op.create_index("ix_pipeline_event_actor_user_id", "pipeline_event", ["actor_user_id"])
    op.create_index("ix_pipeline_event_event_at", "pipeline_event", ["event_at"])


def downgrade():
    op.drop_index("ix_pipeline_event_event_at", table_name="pipeline_event")
    op.drop_index("ix_pipeline_event_actor_user_id", table_name="pipeline_event")
    op.drop_index("ix_pipeline_event_event_type", table_name="pipeline_event")
    op.drop_index("ix_pipeline_event_pipeline_case_id", table_name="pipeline_event")
    op.drop_table("pipeline_event")

    op.drop_index("ix_pipeline_delivery_status", table_name="pipeline_delivery")
    op.drop_index("ix_pipeline_delivery_delivery_number", table_name="pipeline_delivery")
    op.drop_index("ix_pipeline_delivery_sale_id", table_name="pipeline_delivery")
    op.drop_index("ix_pipeline_delivery_pipeline_case_id", table_name="pipeline_delivery")
    op.drop_table("pipeline_delivery")

    op.drop_index("ix_pipeline_case_health_status", table_name="pipeline_case")
    op.drop_index("ix_pipeline_case_delivery_status", table_name="pipeline_case")
    op.drop_index("ix_pipeline_case_payment_status", table_name="pipeline_case")
    op.drop_index("ix_pipeline_case_authorization_status", table_name="pipeline_case")
    op.drop_index("ix_pipeline_case_current_status", table_name="pipeline_case")
    op.drop_index("ix_pipeline_case_current_stage", table_name="pipeline_case")
    op.drop_index("ix_pipeline_case_invoice_id", table_name="pipeline_case")
    op.drop_index("ix_pipeline_case_sale_id", table_name="pipeline_case")
    op.drop_index("ix_pipeline_case_commercial_processing_batch_id", table_name="pipeline_case")
    op.drop_index("ix_pipeline_case_contract_id", table_name="pipeline_case")
    op.drop_index("ix_pipeline_case_buyer_id", table_name="pipeline_case")
    op.drop_index("ix_pipeline_case_case_number", table_name="pipeline_case")
    op.drop_table("pipeline_case")