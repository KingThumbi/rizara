"""add core traceability foundations

Revision ID: d8f3b2a7c901
Revises: c6c9bc53ca23
Create Date: 2026-05-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "d8f3b2a7c901"
down_revision = "c6c9bc53ca23"
branch_labels = None
depends_on = None


def upgrade():
    for table_name in ("goat", "sheep", "cattle"):
        op.add_column(
            table_name,
            sa.Column("trace_code", sa.String(length=80), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("qr_code_token", sa.String(length=128), nullable=True),
        )
        op.create_index(
            f"ix_{table_name}_trace_code",
            table_name,
            ["trace_code"],
            unique=False,
        )
        op.create_index(
            f"ix_{table_name}_qr_code_token",
            table_name,
            ["qr_code_token"],
            unique=False,
        )

    op.add_column(
        "animal_event",
        sa.Column("event_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "animal_event",
        sa.Column("source_module", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "animal_event",
        sa.Column("reference_type", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "animal_event",
        sa.Column("reference_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "animal_event",
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "animal_event",
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_foreign_key(
        "fk_animal_event_created_by_user",
        "animal_event",
        "user",
        ["created_by_user_id"],
        ["id"],
    )
    op.create_index(
        "ix_animal_event_animal",
        "animal_event",
        ["animal_type", "animal_id"],
        unique=False,
    )
    op.create_index(
        "ix_animal_event_type_datetime",
        "animal_event",
        ["event_type", "event_datetime"],
        unique=False,
    )
    op.create_index(
        "ix_animal_event_reference",
        "animal_event",
        ["reference_type", "reference_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_animal_event_reference", table_name="animal_event")
    op.drop_index("ix_animal_event_type_datetime", table_name="animal_event")
    op.drop_index("ix_animal_event_animal", table_name="animal_event")
    op.drop_constraint(
        "fk_animal_event_created_by_user",
        "animal_event",
        type_="foreignkey",
    )
    op.drop_column("animal_event", "created_at")
    op.drop_column("animal_event", "created_by_user_id")
    op.drop_column("animal_event", "reference_id")
    op.drop_column("animal_event", "reference_type")
    op.drop_column("animal_event", "source_module")
    op.drop_column("animal_event", "event_date")

    for table_name in ("cattle", "sheep", "goat"):
        op.drop_index(f"ix_{table_name}_qr_code_token", table_name=table_name)
        op.drop_index(f"ix_{table_name}_trace_code", table_name=table_name)
        op.drop_column(table_name, "qr_code_token")
        op.drop_column(table_name, "trace_code")
