"""add contract_items timestamps

Revision ID: 0326cffb68cf
Revises: 8c3d3e5f64f8
Create Date: 2026-04-23 17:54:50.339044

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0326cffb68cf'
down_revision = '8c3d3e5f64f8'
branch_labels = None
depends_on = None


"""add contract_items timestamps

Revision ID: 0326cffb68cf
Revises: 8c3d3e5f64f8
Create Date: 2026-04-23 17:54:50.339044

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0326cffb68cf'
down_revision = '8c3d3e5f64f8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("contract_items", sa.Column("created_at", sa.DateTime(), nullable=True))
    op.add_column("contract_items", sa.Column("updated_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("contract_items", "updated_at")
    op.drop_column("contract_items", "created_at")