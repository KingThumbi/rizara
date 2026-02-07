"""document updated_at trigger

Revision ID: 8c1a7f2b9d10
Revises: 4f763976a80b
Create Date: 2026-02-07 02:10:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "8c1a7f2b9d10"
down_revision = "4f763976a80b"
branch_labels = None
depends_on = None


def upgrade():
    # Create or replace trigger function
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.set_document_updated_at()
        RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # Drop existing trigger if any, then create a fresh one
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_set_document_updated_at ON public.document;
        CREATE TRIGGER trg_set_document_updated_at
        BEFORE UPDATE ON public.document
        FOR EACH ROW
        EXECUTE FUNCTION public.set_document_updated_at();
        """
    )


def downgrade():
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_set_document_updated_at ON public.document;
        DROP FUNCTION IF EXISTS public.set_document_updated_at();
        """
    )
