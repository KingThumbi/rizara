"""add institutional foundation tables

Revision ID: f4a9c2d7e8b1
Revises: d8f3b2a7c901
Create Date: 2026-05-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "f4a9c2d7e8b1"
down_revision = "d8f3b2a7c901"
branch_labels = None
depends_on = None


def _timestamps(updated: bool = False):
    cols = [sa.Column("created_at", sa.DateTime(), nullable=False)]
    if updated:
        cols.append(sa.Column("updated_at", sa.DateTime(), nullable=False))
    return cols


def _idx(table: str, *columns: str):
    op.create_index(f"ix_{table}_{'_'.join(columns)}", table, list(columns), unique=False)


def _uuid_idx(table: str):
    op.create_index(f"ix_{table}_uuid", table, ["uuid"], unique=True)


def upgrade():
    op.create_table(
        "research_project",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=True),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("hypothesis", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=160), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(updated=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["user.id"]),
        sa.CheckConstraint(
            "category in ('breed_yield','climate_resilience','market_intelligence','processing_efficiency','animal_health','feed_nutrition','export_compliance','other')",
            name="ck_research_project_category",
        ),
        sa.CheckConstraint(
            "status in ('idea','active','paused','completed','archived')",
            name="ck_research_project_status",
        ),
    )
    _uuid_idx("research_project")
    for col in ("code", "category", "status", "owner_user_id", "created_at"):
        _idx("research_project", col)
    _idx("research_project", "is_archived")

    op.create_table(
        "field_observation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("research_project_id", sa.Integer(), nullable=True),
        sa.Column("observation_date", sa.Date(), nullable=True),
        sa.Column("location", sa.String(length=160), nullable=True),
        sa.Column("animal_type", sa.String(length=20), nullable=True),
        sa.Column("observation_type", sa.String(length=30), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("findings", sa.Text(), nullable=True),
        sa.Column("recommended_action", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["research_project_id"], ["research_project.id"]),
    )
    _uuid_idx("field_observation")
    for col in ("research_project_id", "observation_date", "animal_type", "observation_type", "created_by_user_id", "created_at"):
        _idx("field_observation", col)

    op.create_table(
        "market_insight",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("market_region", sa.String(length=30), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("product_focus", sa.String(length=160), nullable=True),
        sa.Column("insight_date", sa.Date(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("opportunity_level", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
    )
    _uuid_idx("market_insight")
    for col in ("market_region", "insight_date", "opportunity_level", "created_at"):
        _idx("market_insight", col)
    _idx("market_insight", "is_archived")

    op.create_table(
        "innovation_proposal",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("problem_statement", sa.Text(), nullable=True),
        sa.Column("proposed_solution", sa.Text(), nullable=True),
        sa.Column("expected_benefit", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        *_timestamps(updated=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["user.id"]),
    )
    _uuid_idx("innovation_proposal")
    for col in ("status", "priority", "owner_user_id", "created_at"):
        _idx("innovation_proposal", col)
    _idx("innovation_proposal", "is_archived")

    op.create_table(
        "research_document",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("document_type", sa.String(length=80), nullable=True),
        sa.Column("file_path", sa.String(length=255), nullable=True),
        sa.Column("external_url", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("research_project_id", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["research_project_id"], ["research_project.id"]),
    )
    _uuid_idx("research_document")
    for col in ("research_project_id", "created_at"):
        _idx("research_document", col)

    op.create_table(
        "donor_organization",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("organization_type", sa.String(length=40), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("website", sa.String(length=255), nullable=True),
        sa.Column("contact_name", sa.String(length=160), nullable=True),
        sa.Column("contact_email", sa.String(length=160), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
    )
    _uuid_idx("donor_organization")
    for col in ("name", "organization_type", "created_at"):
        _idx("donor_organization", col)
    _idx("donor_organization", "is_archived")

    op.create_table(
        "grant_opportunity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("donor_organization_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("focus_area", sa.String(length=160), nullable=True),
        sa.Column("funding_size_min", sa.Numeric(14, 2), nullable=True),
        sa.Column("funding_size_max", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("opportunity_url", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("eligibility_notes", sa.Text(), nullable=True),
        sa.Column("strategic_fit_notes", sa.Text(), nullable=True),
        *_timestamps(updated=True),
        sa.ForeignKeyConstraint(["donor_organization_id"], ["donor_organization.id"]),
    )
    _uuid_idx("grant_opportunity")
    for col in ("donor_organization_id", "focus_area", "deadline", "status", "created_at"):
        _idx("grant_opportunity", col)
    _idx("grant_opportunity", "is_archived")

    op.create_table(
        "grant_application",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("grant_opportunity_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("application_status", sa.String(length=30), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("submission_date", sa.Date(), nullable=True),
        sa.Column("requested_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("awarded_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("project_title", sa.String(length=200), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("internal_owner_user_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(updated=True),
        sa.ForeignKeyConstraint(["grant_opportunity_id"], ["grant_opportunity.id"]),
        sa.ForeignKeyConstraint(["internal_owner_user_id"], ["user.id"]),
    )
    _uuid_idx("grant_application")
    for col in ("grant_opportunity_id", "application_status", "internal_owner_user_id", "created_at"):
        _idx("grant_application", col)
    _idx("grant_application", "is_archived")

    op.create_table(
        "grant_milestone",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("grant_application_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("completion_notes", sa.Text(), nullable=True),
        *_timestamps(updated=True),
        sa.ForeignKeyConstraint(["grant_application_id"], ["grant_application.id"]),
    )
    _uuid_idx("grant_milestone")
    for col in ("grant_application_id", "due_date", "status", "created_at"):
        _idx("grant_milestone", col)

    op.create_table(
        "grant_report",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("grant_application_id", sa.Integer(), nullable=False),
        sa.Column("report_type", sa.String(length=30), nullable=False),
        sa.Column("reporting_period_start", sa.Date(), nullable=True),
        sa.Column("reporting_period_end", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("submitted_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(updated=True),
        sa.ForeignKeyConstraint(["grant_application_id"], ["grant_application.id"]),
    )
    _uuid_idx("grant_report")
    for col in ("grant_application_id", "report_type", "due_date", "status", "created_at"):
        _idx("grant_report", col)

    op.create_table(
        "grant_document",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("grant_application_id", sa.Integer(), nullable=True),
        sa.Column("grant_opportunity_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("document_type", sa.String(length=40), nullable=False),
        sa.Column("file_path", sa.String(length=255), nullable=True),
        sa.Column("external_url", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["grant_application_id"], ["grant_application.id"]),
        sa.ForeignKeyConstraint(["grant_opportunity_id"], ["grant_opportunity.id"]),
    )
    _uuid_idx("grant_document")
    for col in ("grant_application_id", "grant_opportunity_id", "document_type", "created_at"):
        _idx("grant_document", col)

    op.create_table(
        "strategic_project",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("project_code", sa.String(length=80), nullable=True),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("location", sa.String(length=160), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("linked_grant_application_id", sa.Integer(), nullable=True),
        sa.Column("linked_research_project_id", sa.Integer(), nullable=True),
        *_timestamps(updated=True),
        sa.ForeignKeyConstraint(["linked_grant_application_id"], ["grant_application.id"]),
        sa.ForeignKeyConstraint(["linked_research_project_id"], ["research_project.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["user.id"]),
    )
    _uuid_idx("strategic_project")
    for col in ("project_code", "category", "status", "priority", "owner_user_id", "linked_grant_application_id", "linked_research_project_id", "created_at"):
        _idx("strategic_project", col)
    _idx("strategic_project", "is_archived")

    op.create_table(
        "project_workstream",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("strategic_project_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(updated=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["strategic_project_id"], ["strategic_project.id"]),
    )
    _uuid_idx("project_workstream")
    for col in ("strategic_project_id", "category", "owner_user_id", "status", "created_at"):
        _idx("project_workstream", col)

    op.create_table(
        "project_milestone",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("strategic_project_id", sa.Integer(), nullable=False),
        sa.Column("workstream_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("completion_notes", sa.Text(), nullable=True),
        *_timestamps(updated=True),
        sa.ForeignKeyConstraint(["strategic_project_id"], ["strategic_project.id"]),
        sa.ForeignKeyConstraint(["workstream_id"], ["project_workstream.id"]),
    )
    _uuid_idx("project_milestone")
    for col in ("strategic_project_id", "workstream_id", "due_date", "status", "created_at"):
        _idx("project_milestone", col)

    op.create_table(
        "project_task",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("strategic_project_id", sa.Integer(), nullable=False),
        sa.Column("workstream_id", sa.Integer(), nullable=True),
        sa.Column("milestone_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("assigned_to_user_id", sa.Integer(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        *_timestamps(updated=True),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["milestone_id"], ["project_milestone.id"]),
        sa.ForeignKeyConstraint(["strategic_project_id"], ["strategic_project.id"]),
        sa.ForeignKeyConstraint(["workstream_id"], ["project_workstream.id"]),
    )
    _uuid_idx("project_task")
    for col in ("strategic_project_id", "workstream_id", "milestone_id", "assigned_to_user_id", "due_date", "status", "priority", "created_at"):
        _idx("project_task", col)

    op.create_table(
        "project_document",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("strategic_project_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("document_type", sa.String(length=80), nullable=True),
        sa.Column("file_path", sa.String(length=255), nullable=True),
        sa.Column("external_url", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["strategic_project_id"], ["strategic_project.id"]),
    )
    _uuid_idx("project_document")
    for col in ("strategic_project_id", "created_at"):
        _idx("project_document", col)


def downgrade():
    for table in (
        "project_document",
        "project_task",
        "project_milestone",
        "project_workstream",
        "strategic_project",
        "grant_document",
        "grant_report",
        "grant_milestone",
        "grant_application",
        "grant_opportunity",
        "donor_organization",
        "research_document",
        "innovation_proposal",
        "market_insight",
        "field_observation",
        "research_project",
    ):
        op.drop_table(table)
