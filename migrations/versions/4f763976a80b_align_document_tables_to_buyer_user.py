"""align document tables to buyer/user

Revision ID: 4f763976a80b
Revises: ba9643084eed
Create Date: 2026-02-07 00:56:45.366361
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "4f763976a80b"
down_revision = "ba9643084eed"
branch_labels = None
depends_on = None


def upgrade():
    # Create document table
    op.create_table(
        "document",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("buyer_id", sa.Integer(), nullable=False),
        sa.Column("doc_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=True),
        sa.Column("file_sha256", sa.String(length=64), nullable=True),
        sa.Column("issued_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyer.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("buyer_id", "doc_type", "version", name="uq_document_buyer_type_version"),
    )

    # Indexes for document
    op.create_index(op.f("ix_document_buyer_id"), "document", ["buyer_id"], unique=False)
    op.create_index(op.f("ix_document_created_by_user_id"), "document", ["created_by_user_id"], unique=False)
    op.create_index(op.f("ix_document_doc_type"), "document", ["doc_type"], unique=False)
    op.create_index(op.f("ix_document_status"), "document", ["status"], unique=False)
    op.create_index("ix_document_buyer_type_status", "document", ["buyer_id", "doc_type", "status"], unique=False)

    # Create document_signature table
    op.create_table(
        "document_signature",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("signer_type", sa.String(length=30), nullable=False),
        sa.Column("signed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("sign_method", sa.String(length=30), nullable=False),
        sa.Column("signer_name", sa.String(length=160), nullable=False),
        sa.Column("signer_email", sa.String(length=255), nullable=True),
        sa.Column("signature_image_storage_key", sa.String(length=500), nullable=True),
        sa.Column("typed_consent_text", sa.Text(), nullable=True),
        sa.Column("signed_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.CheckConstraint("sign_method in ('drawn','typed','docusign')", name="ck_docsig_sign_method"),
        sa.CheckConstraint("signer_type in ('buyer','rizara_admin','rizara_staff')", name="ck_docsig_signer_type"),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["signed_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Indexes for document_signature
    op.create_index(op.f("ix_document_signature_document_id"), "document_signature", ["document_id"], unique=False)
    op.create_index(
        op.f("ix_document_signature_signed_by_user_id"),
        "document_signature",
        ["signed_by_user_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_document_signature_signed_by_user_id"), table_name="document_signature")
    op.drop_index(op.f("ix_document_signature_document_id"), table_name="document_signature")
    op.drop_table("document_signature")

    op.drop_index("ix_document_buyer_type_status", table_name="document")
    op.drop_index(op.f("ix_document_status"), table_name="document")
    op.drop_index(op.f("ix_document_doc_type"), table_name="document")
    op.drop_index(op.f("ix_document_created_by_user_id"), table_name="document")
    op.drop_index(op.f("ix_document_buyer_id"), table_name="document")
    op.drop_table("document")
