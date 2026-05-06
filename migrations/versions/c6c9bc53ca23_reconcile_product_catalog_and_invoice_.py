"""reconcile product catalog and invoice discount schema

Revision ID: c6c9bc53ca23
Revises: a37936544cc4
Create Date: 2026-05-06 10:50:50.059454

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c6c9bc53ca23'
down_revision = 'a37936544cc4'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS product_catalog (
        id SERIAL PRIMARY KEY,
        name VARCHAR(120) NOT NULL UNIQUE,
        code VARCHAR(40) UNIQUE,
        animal_type VARCHAR(40) NOT NULL,
        product_type VARCHAR(80) NOT NULL,
        unit VARCHAR(20) NOT NULL DEFAULT 'kg',
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        description TEXT,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
        updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
    );
    """)

    op.execute("""
    ALTER TABLE contracts
    ADD COLUMN IF NOT EXISTS product_catalog_id INTEGER;
    """)

    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'fk_contracts_product_catalog'
        ) THEN
            ALTER TABLE contracts
            ADD CONSTRAINT fk_contracts_product_catalog
            FOREIGN KEY (product_catalog_id)
            REFERENCES product_catalog(id);
        END IF;
    END $$;
    """)

    op.execute("""
    ALTER TABLE invoice
    ADD COLUMN IF NOT EXISTS gross_subtotal NUMERIC(14,2) NOT NULL DEFAULT 0;
    """)

    op.execute("""
    ALTER TABLE invoice
    ADD COLUMN IF NOT EXISTS discount_total NUMERIC(14,2) NOT NULL DEFAULT 0;
    """)

    op.execute("""
    ALTER TABLE invoice_item
    ADD COLUMN IF NOT EXISTS gross_unit_price NUMERIC(14,2) NOT NULL DEFAULT 0;
    """)

    op.execute("""
    ALTER TABLE invoice_item
    ADD COLUMN IF NOT EXISTS discount_per_unit NUMERIC(14,2) NOT NULL DEFAULT 0;
    """)

    op.execute("""
    ALTER TABLE invoice_item
    ADD COLUMN IF NOT EXISTS gross_line_total NUMERIC(14,2) NOT NULL DEFAULT 0;
    """)

    op.execute("""
    ALTER TABLE invoice_item
    ADD COLUMN IF NOT EXISTS discount_amount NUMERIC(14,2) NOT NULL DEFAULT 0;
    """)

    op.execute("""
    UPDATE invoice_item
    SET
        gross_unit_price = COALESCE(NULLIF(gross_unit_price, 0), unit_price, 0),
        gross_line_total = COALESCE(NULLIF(gross_line_total, 0), quantity * unit_price, 0),
        discount_per_unit = COALESCE(discount_per_unit, 0),
        discount_amount = COALESCE(discount_amount, 0),
        line_total = COALESCE(line_total, quantity * unit_price, 0);
    """)

    op.execute("""
    UPDATE invoice
    SET
        gross_subtotal = COALESCE((
            SELECT SUM(invoice_item.gross_line_total)
            FROM invoice_item
            WHERE invoice_item.invoice_id = invoice.id
        ), subtotal, 0),
        discount_total = COALESCE((
            SELECT SUM(invoice_item.discount_amount)
            FROM invoice_item
            WHERE invoice_item.invoice_id = invoice.id
        ), 0);
    """)


def downgrade():
    pass