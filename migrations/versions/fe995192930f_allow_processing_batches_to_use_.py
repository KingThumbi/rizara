"""allow processing batches to use multiple aggregation batches

Revision ID: fe995192930f
Revises: 3939f2bc0031
Create Date: 2026-04-29 14:49:03.496052
"""

from alembic import op
import sqlalchemy as sa


revision = "fe995192930f"
down_revision = "3939f2bc0031"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "processing_batch_aggregation_batches",
        sa.Column("processing_batch_id", sa.Integer(), nullable=False),
        sa.Column("aggregation_batch_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["processing_batch_id"],
            ["commercial_processing_batches.id"],
            name="fk_pbagg_processing_batch",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["aggregation_batch_id"],
            ["aggregation_batch.id"],
            name="fk_pbagg_aggregation_batch",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "processing_batch_id",
            "aggregation_batch_id",
            name="pk_processing_batch_aggregation_batches",
        ),
    )


def downgrade():
    op.drop_table("processing_batch_aggregation_batches")