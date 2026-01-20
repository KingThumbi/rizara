"""Add invoice enum status + buyer portal links

Revision ID: 2911c1eaf0e2
Revises: 43849e2df1c0
Create Date: 2026-01-20

NOTE:
This file was recreated because the database is already at this revision
but the migration file went missing. Since the upgrade already ran, this
migration is intentionally a NO-OP.
"""

from alembic import op
import sqlalchemy as sa

revision = "2911c1eaf0e2"
down_revision = "43849e2df1c0"
branch_labels = None
depends_on = None


def upgrade():
    # NO-OP: DB already has these changes applied.
    pass


def downgrade():
    # NO-OP: Avoid unsafe downgrades with auto-named constraints.
    pass
