"""add sale_id to document

Revision ID: 60383f3489ea
Revises: b11820c95687
Create Date: 2026-05-02 21:36:55.522232
"""

from alembic import op
import sqlalchemy as sa


revision = "60383f3489ea"
down_revision = "b11820c95687"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "document",
        sa.Column("sale_id", sa.Integer(), nullable=True),
    )

    op.create_index(
        "ix_document_sale_id",
        "document",
        ["sale_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_document_sale_id_sales",
        "document",
        "sales",
        ["sale_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint(
        "fk_document_sale_id_sales",
        "document",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_document_sale_id",
        table_name="document",
    )

    op.drop_column("document", "sale_id")