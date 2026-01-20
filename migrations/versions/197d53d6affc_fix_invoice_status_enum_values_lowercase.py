"""Fix invoice status enum values (lowercase)

Revision ID: 197d53d6affc
Revises: 2911c1eaf0e2
Create Date: 2026-01-20 23:59:41.009349

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '197d53d6affc'
down_revision = '2911c1eaf0e2'
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
