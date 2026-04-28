"""create commercial_processing_batches table

Revision ID: be90dec940c1
Revises: 34f351b3f74d
Create Date: 2026-04-26 20:29:39.092764
"""

from alembic import op
import sqlalchemy as sa


revision = "be90dec940c1"
down_revision = "34f351b3f74d"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "commercial_processing_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_number", sa.String(length=50), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("processing_date", sa.Date(), nullable=True),
        sa.Column("source_type", sa.String(length=30), nullable=True),
        sa.Column("source_reference_id", sa.Integer(), nullable=True),
        sa.Column("planned_input_qty", sa.Numeric(14, 2), nullable=True),
        sa.Column("actual_input_qty", sa.Numeric(14, 2), nullable=True),
        sa.Column("output_qty", sa.Numeric(14, 2), nullable=True),
        sa.Column("yield_percentage", sa.Numeric(8, 2), nullable=True),
        sa.Column("processing_authorized", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("authorization_status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("authorization_basis", sa.String(length=30), nullable=True),
        sa.Column("authorization_note", sa.Text(), nullable=True),
        sa.Column("authorized_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),

        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
    )

    op.create_index(
        "ix_commercial_processing_batches_batch_number",
        "commercial_processing_batches",
        ["batch_number"],
        unique=True,
    )

    op.create_index(
        "ix_commercial_processing_batches_contract_id",
        "commercial_processing_batches",
        ["contract_id"],
        unique=False,
    )

    op.create_index(
        "ix_commercial_processing_batches_status",
        "commercial_processing_batches",
        ["status"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_commercial_processing_batches_status",
        table_name="commercial_processing_batches",
    )

    op.drop_index(
        "ix_commercial_processing_batches_contract_id",
        table_name="commercial_processing_batches",
    )

    op.drop_index(
        "ix_commercial_processing_batches_batch_number",
        table_name="commercial_processing_batches",
    )

    op.drop_table("commercial_processing_batches")