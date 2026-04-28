"""add procurement_record_id to animals"""

from alembic import op
import sqlalchemy as sa

revision = "e6b08903bacf"
down_revision = "5f986bcac231"
branch_labels = None
depends_on = None


def upgrade():
    # Only add constraints (columns already exist)

    op.create_foreign_key(
        "fk_goat_procurement_record",
        "goat",
        "procurement_records",
        ["procurement_record_id"],
        ["id"],
    )

    op.create_foreign_key(
        "fk_sheep_procurement_record",
        "sheep",
        "procurement_records",
        ["procurement_record_id"],
        ["id"],
    )

    op.create_foreign_key(
        "fk_cattle_procurement_record",
        "cattle",
        "procurement_records",
        ["procurement_record_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint("fk_cattle_procurement_record", "cattle", type_="foreignkey")
    op.drop_constraint("fk_sheep_procurement_record", "sheep", type_="foreignkey")
    op.drop_constraint("fk_goat_procurement_record", "goat", type_="foreignkey")