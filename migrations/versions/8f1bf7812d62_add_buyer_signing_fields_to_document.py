"""add buyer signing fields to document

Revision ID: 8f1bf7812d62
Revises: 8c1a7f2b9d10
Create Date: 2026-02-08 16:50:17.816428

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8f1bf7812d62'
down_revision = '8c1a7f2b9d10'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("document", sa.Column("buyer_sign_token", sa.String(length=128), nullable=True))
    op.add_column("document", sa.Column("buyer_sign_token_expires_at", sa.DateTime(), nullable=True))
    op.add_column("document", sa.Column("buyer_signed_at", sa.DateTime(), nullable=True))
    op.add_column("document", sa.Column("buyer_sign_name", sa.String(length=160), nullable=True))
    op.add_column("document", sa.Column("buyer_sign_email", sa.String(length=120), nullable=True))
    op.add_column("document", sa.Column("buyer_sign_ip", sa.String(length=64), nullable=True))
    op.add_column("document", sa.Column("buyer_sign_user_agent", sa.String(length=255), nullable=True))

    # (Optional but useful) index for token lookups during signing flow
    op.create_index("ix_document_buyer_sign_token", "document", ["buyer_sign_token"], unique=False)


def downgrade():
    op.drop_index("ix_document_buyer_sign_token", table_name="document")
    op.drop_column("document", "buyer_sign_user_agent")
    op.drop_column("document", "buyer_sign_ip")
    op.drop_column("document", "buyer_sign_email")
    op.drop_column("document", "buyer_sign_name")
    op.drop_column("document", "buyer_signed_at")
    op.drop_column("document", "buyer_sign_token_expires_at")
    op.drop_column("document", "buyer_sign_token")