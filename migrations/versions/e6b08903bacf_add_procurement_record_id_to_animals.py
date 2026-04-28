"""add procurement_record_id to animals"""

from alembic import op
from sqlalchemy import inspect


revision = "e6b08903bacf"
down_revision = "5f986bcac231"
branch_labels = None
depends_on = None


def _foreign_key_exists(table_name: str, constraint_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return any(
        fk.get("name") == constraint_name
        for fk in inspector.get_foreign_keys(table_name)
    )


def upgrade():
    if not _foreign_key_exists("goat", "fk_goat_procurement_record"):
        op.create_foreign_key(
            "fk_goat_procurement_record",
            "goat",
            "procurement_records",
            ["procurement_record_id"],
            ["id"],
        )

    if not _foreign_key_exists("sheep", "fk_sheep_procurement_record"):
        op.create_foreign_key(
            "fk_sheep_procurement_record",
            "sheep",
            "procurement_records",
            ["procurement_record_id"],
            ["id"],
        )

    if not _foreign_key_exists("cattle", "fk_cattle_procurement_record"):
        op.create_foreign_key(
            "fk_cattle_procurement_record",
            "cattle",
            "procurement_records",
            ["procurement_record_id"],
            ["id"],
        )


def downgrade():
    if _foreign_key_exists("cattle", "fk_cattle_procurement_record"):
        op.drop_constraint("fk_cattle_procurement_record", "cattle", type_="foreignkey")

    if _foreign_key_exists("sheep", "fk_sheep_procurement_record"):
        op.drop_constraint("fk_sheep_procurement_record", "sheep", type_="foreignkey")

    if _foreign_key_exists("goat", "fk_goat_procurement_record"):
        op.drop_constraint("fk_goat_procurement_record", "goat", type_="foreignkey")