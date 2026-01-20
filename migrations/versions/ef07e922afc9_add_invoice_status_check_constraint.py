"""Add invoice status check constraint

Revision ID: ef07e922afc9
Revises: 197d53d6affc
Create Date: 2026-01-21 00:19:57.146087
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "ef07e922afc9"
down_revision = "197d53d6affc"
branch_labels = None
depends_on = None


def upgrade():
    # Normalize existing values
    op.execute("UPDATE public.invoice SET status = lower(status) WHERE status IS NOT NULL;")

    # Add DB-level enforcement (explicit schema)
    op.execute("""
        ALTER TABLE public.invoice
        ADD CONSTRAINT ck_invoice_status
        CHECK (status IN ('draft','issued','paid','void'));
    """)


def downgrade():
    # Safe downgrade (won't crash if constraint is missing)
    op.execute("ALTER TABLE public.invoice DROP CONSTRAINT IF EXISTS ck_invoice_status;")
