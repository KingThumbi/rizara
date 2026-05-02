"""add timestamps to sale_items"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "0ee518a98b3a"
down_revision = "fe570bef9df8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "sale_items",
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.add_column(
        "sale_items",
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_column("sale_items", "updated_at")
    op.drop_column("sale_items", "created_at")