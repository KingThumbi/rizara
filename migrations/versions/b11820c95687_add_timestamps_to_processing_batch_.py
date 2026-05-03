"""add timestamps to processing_batch_outputs

Revision ID: b11820c95687
Revises: 0ee518a98b3a
Create Date: 2026-05-01 15:59:19.469911

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b11820c95687'
down_revision = '0ee518a98b3a'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "processing_batch_outputs",
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "processing_batch_outputs",
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.execute("""
        UPDATE processing_batch_outputs
        SET created_at = NOW(),
            updated_at = NOW()
        WHERE created_at IS NULL
           OR updated_at IS NULL
    """)

    op.alter_column("processing_batch_outputs", "created_at", nullable=False)
    op.alter_column("processing_batch_outputs", "updated_at", nullable=False)


def downgrade():
    op.drop_column("processing_batch_outputs", "updated_at")
    op.drop_column("processing_batch_outputs", "created_at")