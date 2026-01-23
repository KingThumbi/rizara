"""Add accepted_terms fields to user (fix)

Revision ID: ba9643084eed
Revises: a02201e1ebe0
Create Date: 2026-01-23 18:19:41.730584

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ba9643084eed'
down_revision = 'a02201e1ebe0'
branch_labels = None
depends_on = None


def upgrade():
    # Postgres-safe: won't crash if columns already exist
    op.execute(sa.text(
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS accepted_terms BOOLEAN DEFAULT false NOT NULL;'
    ))
    op.execute(sa.text(
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS accepted_terms_at TIMESTAMP;'
    ))
    op.execute(sa.text(
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS terms_version VARCHAR(20);'
    ))

    # Optional: remove default so future inserts rely on app logic (matches original intent)
    op.execute(sa.text(
        'ALTER TABLE "user" ALTER COLUMN accepted_terms DROP DEFAULT;'
    ))


def downgrade():
    # Safe downgrade
    op.execute(sa.text('ALTER TABLE "user" DROP COLUMN IF EXISTS terms_version;'))
    op.execute(sa.text('ALTER TABLE "user" DROP COLUMN IF EXISTS accepted_terms_at;'))
    op.execute(sa.text('ALTER TABLE "user" DROP COLUMN IF EXISTS accepted_terms;'))
