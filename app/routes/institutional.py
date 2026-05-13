from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

import sqlalchemy as sa
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.models import (
    FieldObservation,
    GrantApplication,
    GrantMilestone,
    GrantOpportunity,
    GrantReport,
    InnovationProposal,
    MarketInsight,
    ProjectMilestone,
    ProjectTask,
    ResearchProject,
    StrategicProject,
)
from app.utils.guards import admin_required


institutional_bp = Blueprint("institutional", __name__, url_prefix="/admin")

RESEARCH_CATEGORIES = [
    "breed_yield",
    "climate_resilience",
    "market_intelligence",
    "processing_efficiency",
    "animal_health",
    "feed_nutrition",
    "export_compliance",
    "other",
]
RESEARCH_STATUSES = ["idea", "active", "paused", "completed", "archived"]
GRANT_STATUSES = [
    "identified",
    "researching",
    "drafting",
    "submitted",
    "shortlisted",
    "awarded",
    "declined",
    "archived",
]
PROJECT_CATEGORIES = [
    "grant",
    "operations",
    "traceability",
    "export_readiness",
    "infrastructure",
    "farmer_onboarding",
    "research",
    "compliance",
    "other",
]
PROJECT_STATUSES = ["planned", "active", "paused", "completed", "cancelled", "archived"]
PROJECT_PRIORITIES = ["low", "medium", "high", "critical"]


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _parse_date(value: str | None) -> date | None:
    value = _clean(value)
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_money(value: str | None) -> Decimal | None:
    value = _clean(value)
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _commit_or_rollback(action: str) -> bool:
    try:
        db.session.commit()
        flash(f"{action} saved.", "success")
        return True
    except Exception as exc:
        db.session.rollback()
        flash(f"{action} failed: {exc}", "danger")
        return False


def _current_admin_id() -> int | None:
    return getattr(current_user, "id", None) if getattr(current_user, "is_authenticated", False) else None


@institutional_bp.route("/research", methods=["GET"])
@admin_required
def research_index():
    projects = ResearchProject.query.filter(ResearchProject.is_archived.is_(False)).order_by(
        ResearchProject.created_at.desc()
    ).limit(100).all()
    stats = {
        "active_projects": ResearchProject.query.filter(
            ResearchProject.is_archived.is_(False),
            ResearchProject.status == "active",
        ).count(),
        "recent_observations": FieldObservation.query.count(),
        "active_proposals": InnovationProposal.query.filter(
            InnovationProposal.is_archived.is_(False),
            InnovationProposal.status.in_(["proposed", "under_review", "pilot", "approved"]),
        ).count(),
        "high_market_insights": MarketInsight.query.filter(
            MarketInsight.is_archived.is_(False),
            MarketInsight.opportunity_level == "high",
        ).count(),
    }
    recent_observations = FieldObservation.query.order_by(FieldObservation.created_at.desc()).limit(5).all()
    high_insights = MarketInsight.query.filter(
        MarketInsight.is_archived.is_(False),
        MarketInsight.opportunity_level == "high",
    ).order_by(MarketInsight.created_at.desc()).limit(5).all()
    return render_template(
        "admin/institutional/research_index.html",
        projects=projects,
        stats=stats,
        recent_observations=recent_observations,
        high_insights=high_insights,
    )


@institutional_bp.route("/research/new", methods=["GET", "POST"])
@admin_required
def research_new():
    project = ResearchProject()
    if request.method == "POST":
        _populate_research_project(project)
        db.session.add(project)
        if _commit_or_rollback("Research project"):
            return redirect(url_for("institutional.research_detail", project_id=project.id))
    return render_template(
        "admin/institutional/research_form.html",
        project=project,
        categories=RESEARCH_CATEGORIES,
        statuses=RESEARCH_STATUSES,
        action="Create",
    )


@institutional_bp.route("/research/<int:project_id>", methods=["GET"])
@admin_required
def research_detail(project_id: int):
    project = ResearchProject.query.get_or_404(project_id)
    return render_template("admin/institutional/research_detail.html", project=project)


@institutional_bp.route("/research/<int:project_id>/edit", methods=["GET", "POST"])
@admin_required
def research_edit(project_id: int):
    project = ResearchProject.query.get_or_404(project_id)
    if request.method == "POST":
        _populate_research_project(project)
        if _commit_or_rollback("Research project"):
            return redirect(url_for("institutional.research_detail", project_id=project.id))
    return render_template(
        "admin/institutional/research_form.html",
        project=project,
        categories=RESEARCH_CATEGORIES,
        statuses=RESEARCH_STATUSES,
        action="Update",
    )


def _populate_research_project(project: ResearchProject) -> None:
    project.title = _clean(request.form.get("title")) or "Untitled research project"
    project.code = _clean(request.form.get("code"))
    project.category = request.form.get("category") if request.form.get("category") in RESEARCH_CATEGORIES else "other"
    project.status = request.form.get("status") if request.form.get("status") in RESEARCH_STATUSES else "idea"
    project.objective = _clean(request.form.get("objective"))
    project.hypothesis = _clean(request.form.get("hypothesis"))
    project.location = _clean(request.form.get("location"))
    project.start_date = _parse_date(request.form.get("start_date"))
    project.end_date = _parse_date(request.form.get("end_date"))
    project.notes = _clean(request.form.get("notes"))
    project.owner_user_id = project.owner_user_id or _current_admin_id()


@institutional_bp.route("/grants", methods=["GET"])
@admin_required
def grants_index():
    opportunities = GrantOpportunity.query.filter(GrantOpportunity.is_archived.is_(False)).order_by(
        sa.nullslast(GrantOpportunity.deadline.asc()),
        GrantOpportunity.created_at.desc(),
    ).limit(100).all()
    application_statuses = dict(
        db.session.query(GrantApplication.application_status, sa.func.count(GrantApplication.id))
        .filter(GrantApplication.is_archived.is_(False))
        .group_by(GrantApplication.application_status)
        .all()
    )
    stats = {
        "active_opportunities": GrantOpportunity.query.filter(
            GrantOpportunity.is_archived.is_(False),
            GrantOpportunity.status.in_(["identified", "researching", "drafting", "submitted", "shortlisted"]),
        ).count(),
        "upcoming_deadlines": GrantOpportunity.query.filter(
            GrantOpportunity.is_archived.is_(False),
            GrantOpportunity.deadline.isnot(None),
            GrantOpportunity.deadline >= date.today(),
            GrantOpportunity.status.notin_(["awarded", "declined", "archived"]),
        ).count(),
        "pending_milestones": GrantMilestone.query.filter(
            GrantMilestone.status.in_(["pending", "in_progress", "delayed"])
        ).count(),
        "pending_reports": GrantReport.query.filter(GrantReport.status.in_(["draft", "revision_requested"])).count(),
    }
    upcoming = GrantOpportunity.query.filter(
        GrantOpportunity.is_archived.is_(False),
        GrantOpportunity.deadline.isnot(None),
    ).order_by(GrantOpportunity.deadline.asc()).limit(5).all()
    return render_template(
        "admin/institutional/grants_index.html",
        opportunities=opportunities,
        application_statuses=application_statuses,
        stats=stats,
        upcoming=upcoming,
    )


@institutional_bp.route("/grants/new", methods=["GET", "POST"])
@admin_required
def grants_new():
    opportunity = GrantOpportunity()
    if request.method == "POST":
        _populate_grant_opportunity(opportunity)
        db.session.add(opportunity)
        if _commit_or_rollback("Grant opportunity"):
            return redirect(url_for("institutional.grants_detail", opportunity_id=opportunity.id))
    return render_template(
        "admin/institutional/grants_form.html",
        opportunity=opportunity,
        statuses=GRANT_STATUSES,
        action="Create",
    )


@institutional_bp.route("/grants/<int:opportunity_id>", methods=["GET"])
@admin_required
def grants_detail(opportunity_id: int):
    opportunity = GrantOpportunity.query.get_or_404(opportunity_id)
    return render_template("admin/institutional/grants_detail.html", opportunity=opportunity)


@institutional_bp.route("/grants/<int:opportunity_id>/edit", methods=["GET", "POST"])
@admin_required
def grants_edit(opportunity_id: int):
    opportunity = GrantOpportunity.query.get_or_404(opportunity_id)
    if request.method == "POST":
        _populate_grant_opportunity(opportunity)
        if _commit_or_rollback("Grant opportunity"):
            return redirect(url_for("institutional.grants_detail", opportunity_id=opportunity.id))
    return render_template(
        "admin/institutional/grants_form.html",
        opportunity=opportunity,
        statuses=GRANT_STATUSES,
        action="Update",
    )


def _populate_grant_opportunity(opportunity: GrantOpportunity) -> None:
    opportunity.title = _clean(request.form.get("title")) or "Untitled grant opportunity"
    opportunity.focus_area = _clean(request.form.get("focus_area"))
    opportunity.funding_size_min = _parse_money(request.form.get("funding_size_min"))
    opportunity.funding_size_max = _parse_money(request.form.get("funding_size_max"))
    opportunity.currency = _clean(request.form.get("currency")) or "USD"
    opportunity.deadline = _parse_date(request.form.get("deadline"))
    opportunity.opportunity_url = _clean(request.form.get("opportunity_url"))
    opportunity.status = request.form.get("status") if request.form.get("status") in GRANT_STATUSES else "identified"
    opportunity.eligibility_notes = _clean(request.form.get("eligibility_notes"))
    opportunity.strategic_fit_notes = _clean(request.form.get("strategic_fit_notes"))


@institutional_bp.route("/projects", methods=["GET"])
@admin_required
def projects_index():
    projects = StrategicProject.query.filter(StrategicProject.is_archived.is_(False)).order_by(
        StrategicProject.created_at.desc()
    ).limit(100).all()
    projects_by_status = dict(
        db.session.query(StrategicProject.status, sa.func.count(StrategicProject.id))
        .filter(StrategicProject.is_archived.is_(False))
        .group_by(StrategicProject.status)
        .all()
    )
    today = date.today()
    stats = {
        "active_projects": StrategicProject.query.filter(
            StrategicProject.is_archived.is_(False),
            StrategicProject.status == "active",
        ).count(),
        "overdue_milestones": ProjectMilestone.query.filter(
            ProjectMilestone.due_date < today,
            ProjectMilestone.status.notin_(["completed"]),
        ).count(),
        "overdue_tasks": ProjectTask.query.filter(
            ProjectTask.due_date < today,
            ProjectTask.status.notin_(["done", "cancelled"]),
        ).count(),
        "linked_records": StrategicProject.query.filter(
            StrategicProject.is_archived.is_(False),
            sa.or_(
                StrategicProject.linked_grant_application_id.isnot(None),
                StrategicProject.linked_research_project_id.isnot(None),
            )
        ).count(),
    }
    return render_template(
        "admin/institutional/projects_index.html",
        projects=projects,
        projects_by_status=projects_by_status,
        stats=stats,
    )


@institutional_bp.route("/projects/new", methods=["GET", "POST"])
@admin_required
def projects_new():
    project = StrategicProject()
    if request.method == "POST":
        _populate_strategic_project(project)
        db.session.add(project)
        if _commit_or_rollback("Strategic project"):
            return redirect(url_for("institutional.projects_detail", project_id=project.id))
    return render_template(
        "admin/institutional/projects_form.html",
        project=project,
        categories=PROJECT_CATEGORIES,
        statuses=PROJECT_STATUSES,
        priorities=PROJECT_PRIORITIES,
        action="Create",
    )


@institutional_bp.route("/projects/<int:project_id>", methods=["GET"])
@admin_required
def projects_detail(project_id: int):
    project = StrategicProject.query.get_or_404(project_id)
    return render_template("admin/institutional/projects_detail.html", project=project)


@institutional_bp.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
@admin_required
def projects_edit(project_id: int):
    project = StrategicProject.query.get_or_404(project_id)
    if request.method == "POST":
        _populate_strategic_project(project)
        if _commit_or_rollback("Strategic project"):
            return redirect(url_for("institutional.projects_detail", project_id=project.id))
    return render_template(
        "admin/institutional/projects_form.html",
        project=project,
        categories=PROJECT_CATEGORIES,
        statuses=PROJECT_STATUSES,
        priorities=PROJECT_PRIORITIES,
        action="Update",
    )


def _populate_strategic_project(project: StrategicProject) -> None:
    project.title = _clean(request.form.get("title")) or "Untitled strategic project"
    project.project_code = _clean(request.form.get("project_code"))
    project.category = request.form.get("category") if request.form.get("category") in PROJECT_CATEGORIES else "other"
    project.status = request.form.get("status") if request.form.get("status") in PROJECT_STATUSES else "planned"
    project.priority = request.form.get("priority") if request.form.get("priority") in PROJECT_PRIORITIES else "medium"
    project.start_date = _parse_date(request.form.get("start_date"))
    project.end_date = _parse_date(request.form.get("end_date"))
    project.location = _clean(request.form.get("location"))
    project.description = _clean(request.form.get("description"))
    project.objective = _clean(request.form.get("objective"))
    project.owner_user_id = project.owner_user_id or _current_admin_id()
