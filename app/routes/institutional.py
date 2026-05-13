from __future__ import annotations

import csv
from io import StringIO
from datetime import date
from decimal import Decimal, InvalidOperation

import sqlalchemy as sa
from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.models import (
    EvidenceRecord,
    FieldObservation,
    GrantApplication,
    GrantDocument,
    GrantImpactMetric,
    GrantMilestone,
    GrantOpportunity,
    GrantReport,
    ImpactSnapshot,
    InnovationProposal,
    MarketInsight,
    ProjectMilestone,
    ProjectTask,
    ResearchProject,
    StrategicProject,
)
from app.utils.guards import admin_required
from app.constants.impact_metrics import IMPACT_METRICS
from app.services.impact_metrics import (
    calculate_impact_metrics,
    create_current_impact_snapshot,
    group_metrics,
)
from app.services.reporting import assemble_grant_reporting_package, grant_reporting_export_rows


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
GRANT_APPLICATION_STATUSES = ["drafting", "submitted", "under_review", "shortlisted", "awarded", "declined", "withdrawn"]
GRANT_MILESTONE_STATUSES = ["pending", "in_progress", "completed", "delayed", "waived"]
GRANT_REPORT_TYPES = ["narrative", "financial", "impact", "milestone", "final"]
GRANT_REPORT_STATUSES = ["draft", "submitted", "accepted", "revision_requested"]
GRANT_DOCUMENT_TYPES = ["concept_note", "proposal", "budget", "deck", "contract", "report", "attachment", "other"]
GRANT_IMPACT_METRIC_TYPES = ["output", "outcome", "impact", "financial", "compliance", "other"]
GRANT_IMPACT_METRIC_STATUSES = ["planned", "in_progress", "achieved", "at_risk", "missed"]
EVIDENCE_TYPES = [
    "field_photo",
    "attendance",
    "beneficiary_record",
    "invoice",
    "export_document",
    "aggregation_record",
    "training_record",
    "milestone_proof",
    "other",
]
EVIDENCE_LINK_TYPES = ["GrantReport", "GrantMilestone", "GrantImpactMetric", "StrategicProject", "ResearchProject"]
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


def _grant_application_query():
    return GrantApplication.query.filter(GrantApplication.is_archived.is_(False))


def _grant_opportunity_query():
    return GrantOpportunity.query.filter(GrantOpportunity.is_archived.is_(False))


def _snapshot_filters():
    return {
        "start_date": _clean(request.args.get("start_date")),
        "end_date": _clean(request.args.get("end_date")),
        "metric_category": _clean(request.args.get("metric_category")),
        "county": _clean(request.args.get("county")),
        "animal_type": _clean(request.args.get("animal_type")),
        "metric_code": _clean(request.args.get("metric_code")),
    }


def _filtered_snapshot_query(filters: dict[str, str | None]):
    query = ImpactSnapshot.query
    if filters.get("start_date"):
        query = query.filter(ImpactSnapshot.snapshot_date >= date.fromisoformat(filters["start_date"]))
    if filters.get("end_date"):
        query = query.filter(ImpactSnapshot.snapshot_date <= date.fromisoformat(filters["end_date"]))
    if filters.get("metric_category"):
        query = query.filter(ImpactSnapshot.metric_category == filters["metric_category"])
    if filters.get("county"):
        query = query.filter(ImpactSnapshot.county == filters["county"])
    if filters.get("animal_type"):
        query = query.filter(ImpactSnapshot.animal_type == filters["animal_type"])
    if filters.get("metric_code"):
        query = query.filter(ImpactSnapshot.metric_code == filters["metric_code"])
    return query


def _csv_response(filename: str, rows: list[dict], fieldnames: list[str]) -> Response:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@institutional_bp.route("/impact", methods=["GET"])
@admin_required
def impact_dashboard():
    metrics = calculate_impact_metrics()
    filters = _snapshot_filters()
    page = max(int(request.args.get("page", 1) or 1), 1)
    per_page = 25
    snapshot_query = _filtered_snapshot_query(filters).order_by(
        ImpactSnapshot.snapshot_date.desc(),
        ImpactSnapshot.created_at.desc(),
    )
    recent_snapshots = snapshot_query.limit(30).all()
    snapshot_page = snapshot_query.paginate(page=page, per_page=per_page, error_out=False)
    latest_snapshot = ImpactSnapshot.query.order_by(
        ImpactSnapshot.snapshot_date.desc(),
        ImpactSnapshot.created_at.desc(),
    ).first()
    top_categories = (
        db.session.query(ImpactSnapshot.metric_category, sa.func.count(ImpactSnapshot.id))
        .group_by(ImpactSnapshot.metric_category)
        .order_by(sa.func.count(ImpactSnapshot.id).desc())
        .limit(5)
        .all()
    )
    grant_summary = {
        "active": GrantApplication.query.filter(
            GrantApplication.is_archived.is_(False),
            GrantApplication.application_status.in_(["drafting", "submitted", "under_review", "shortlisted", "awarded"]),
        ).count(),
        "awarded": GrantApplication.query.filter(
            GrantApplication.is_archived.is_(False),
            GrantApplication.application_status == "awarded",
        ).count(),
        "overdue_reports": GrantReport.query.filter(
            GrantReport.due_date.isnot(None),
            GrantReport.due_date < date.today(),
            GrantReport.status.notin_(["submitted", "accepted"]),
        ).count(),
        "active_reporting_periods": GrantReport.query.filter(
            GrantReport.status.in_(["draft", "revision_requested"]),
            GrantReport.reporting_period_start.isnot(None),
            GrantReport.reporting_period_end.isnot(None),
        ).count(),
    }
    project_summary = {
        "active": StrategicProject.query.filter(
            StrategicProject.is_archived.is_(False),
            StrategicProject.status == "active",
        ).count(),
        "planned": StrategicProject.query.filter(
            StrategicProject.is_archived.is_(False),
            StrategicProject.status == "planned",
        ).count(),
        "completed": StrategicProject.query.filter(
            StrategicProject.is_archived.is_(False),
            StrategicProject.status == "completed",
        ).count(),
    }
    return render_template(
        "admin/institutional/impact_dashboard.html",
        metrics=metrics,
        grouped_metrics=group_metrics(metrics),
        recent_snapshots=recent_snapshots,
        snapshot_page=snapshot_page,
        filters=filters,
        metric_categories=sorted({definition.category for definition in IMPACT_METRICS.values()}),
        metric_codes=sorted(IMPACT_METRICS),
        latest_snapshot=latest_snapshot,
        top_categories=top_categories,
        evidence_count=EvidenceRecord.query.count(),
        grant_summary=grant_summary,
        project_summary=project_summary,
    )


@institutional_bp.route("/impact/snapshots/generate", methods=["POST"])
@admin_required
def impact_snapshot_generate():
    snapshots = create_current_impact_snapshot()
    if _commit_or_rollback("Impact snapshot"):
        flash(f"Generated {len(snapshots)} impact snapshot metrics.", "success")
    return redirect(url_for("institutional.impact_dashboard"))


@institutional_bp.route("/impact/export.csv", methods=["GET"])
@admin_required
def impact_export_csv():
    filters = _snapshot_filters()
    snapshots = _filtered_snapshot_query(filters).order_by(
        ImpactSnapshot.snapshot_date.desc(),
        ImpactSnapshot.created_at.desc(),
    ).all()
    rows = [
        {
            "snapshot_date": snapshot.snapshot_date,
            "metric_code": snapshot.metric_code,
            "metric_name": snapshot.metric_name,
            "category": snapshot.metric_category,
            "metric_value": snapshot.metric_value,
            "metric_unit": snapshot.metric_unit,
            "source_module": snapshot.source_module,
            "county": snapshot.county,
            "animal_type": snapshot.animal_type,
            "created_at": snapshot.created_at,
        }
        for snapshot in snapshots
    ]
    return _csv_response(
        "impact_snapshots.csv",
        rows,
        [
            "snapshot_date",
            "metric_code",
            "metric_name",
            "category",
            "metric_value",
            "metric_unit",
            "source_module",
            "county",
            "animal_type",
            "created_at",
        ],
    )


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
    opportunities = _grant_opportunity_query().order_by(
        sa.nullslast(GrantOpportunity.deadline.asc()),
        GrantOpportunity.created_at.desc(),
    ).limit(100).all()
    recent_applications = _grant_application_query().order_by(
        GrantApplication.created_at.desc()
    ).limit(8).all()
    application_statuses = dict(
        db.session.query(GrantApplication.application_status, sa.func.count(GrantApplication.id))
        .filter(GrantApplication.is_archived.is_(False))
        .group_by(GrantApplication.application_status)
        .all()
    )
    stats = {
        "active_opportunities": _grant_opportunity_query().filter(
            GrantOpportunity.status.in_(["identified", "researching", "drafting", "submitted", "shortlisted"]),
        ).count(),
        "active_applications": _grant_application_query().filter(
            GrantApplication.application_status.in_(["drafting", "submitted", "under_review", "shortlisted", "awarded"])
        ).count(),
        "upcoming_deadlines": _grant_opportunity_query().filter(
            GrantOpportunity.deadline.isnot(None),
            GrantOpportunity.deadline >= date.today(),
            GrantOpportunity.status.notin_(["awarded", "declined", "archived"]),
        ).count(),
        "pending_milestones": GrantMilestone.query.filter(
            GrantMilestone.status.in_(["pending", "in_progress", "delayed"])
        ).count(),
        "pending_reports": GrantReport.query.filter(GrantReport.status.in_(["draft", "revision_requested"])).count(),
    }
    upcoming = _grant_opportunity_query().filter(
        GrantOpportunity.deadline.isnot(None),
    ).order_by(GrantOpportunity.deadline.asc()).limit(5).all()
    return render_template(
        "admin/institutional/grants_index.html",
        opportunities=opportunities,
        recent_applications=recent_applications,
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


@institutional_bp.route("/grants/applications", methods=["GET"])
@admin_required
def grant_applications_index():
    applications = _grant_application_query().order_by(GrantApplication.created_at.desc()).limit(150).all()
    return render_template(
        "admin/institutional/grant_applications_index.html",
        applications=applications,
    )


@institutional_bp.route("/grants/applications/new", methods=["GET", "POST"])
@admin_required
def grant_applications_new():
    application = GrantApplication()
    opportunity_id = request.args.get("opportunity_id") or request.form.get("grant_opportunity_id")
    if opportunity_id:
        application.grant_opportunity_id = int(opportunity_id)

    if request.method == "POST":
        _populate_grant_application(application)
        db.session.add(application)
        if _commit_or_rollback("Grant application"):
            return redirect(url_for("institutional.grant_applications_detail", application_id=application.id))

    return render_template(
        "admin/institutional/grant_application_form.html",
        application=application,
        opportunities=_grant_opportunity_query().order_by(GrantOpportunity.title.asc()).all(),
        statuses=GRANT_APPLICATION_STATUSES,
        action="Create",
    )


@institutional_bp.route("/grants/applications/<int:application_id>", methods=["GET"])
@admin_required
def grant_applications_detail(application_id: int):
    application = GrantApplication.query.get_or_404(application_id)
    reporting_package = assemble_grant_reporting_package(application.id)
    milestones = GrantMilestone.query.filter_by(grant_application_id=application.id).order_by(
        sa.nullslast(GrantMilestone.due_date.asc()),
        GrantMilestone.created_at.desc(),
    ).all()
    reports = GrantReport.query.filter_by(grant_application_id=application.id).order_by(
        sa.nullslast(GrantReport.due_date.asc()),
        GrantReport.created_at.desc(),
    ).all()
    impact_metrics = GrantImpactMetric.query.filter_by(grant_application_id=application.id).order_by(
        GrantImpactMetric.created_at.desc()
    ).all()
    documents = GrantDocument.query.filter_by(grant_application_id=application.id).order_by(
        GrantDocument.created_at.desc()
    ).all()
    return render_template(
        "admin/institutional/grant_application_detail.html",
        application=application,
        milestones=milestones,
        reports=reports,
        impact_metrics=impact_metrics,
        documents=documents,
        reporting_package=reporting_package,
    )


@institutional_bp.route("/grants/applications/<int:application_id>/report-preview", methods=["GET"])
@admin_required
def grant_application_report_preview(application_id: int):
    package = assemble_grant_reporting_package(application_id)
    readiness_notes = []
    if not package["milestones"]:
        readiness_notes.append("Add milestones to show implementation progress.")
    if not package["reports"]:
        readiness_notes.append("Add reporting records to clarify donor obligations.")
    if not package["impact_metrics"]:
        readiness_notes.append("Add impact metrics or link operational metrics for donor-ready results.")

    evidence_count = sum(len(item["evidence"]) for item in package["milestones"])
    evidence_count += sum(len(item["evidence"]) for item in package["reports"])
    evidence_count += sum(len(item["evidence"]) for item in package["impact_metrics"])
    if not evidence_count:
        readiness_notes.append("Attach evidence records for stronger verification.")

    return render_template(
        "admin/institutional/grant_report_preview.html",
        package=package,
        application=package["application"],
        opportunity=package["opportunity"],
        readiness_notes=readiness_notes,
        evidence_count=evidence_count,
    )


@institutional_bp.route("/grants/applications/<int:application_id>/report-export.csv", methods=["GET"])
@admin_required
def grant_application_report_export_csv(application_id: int):
    rows = grant_reporting_export_rows(application_id)
    return _csv_response(
        f"grant_application_{application_id}_reporting_package.csv",
        rows,
        [
            "record_type",
            "title",
            "status",
            "due_date",
            "submitted_or_completed_date",
            "metric_code",
            "value",
            "unit",
            "evidence_count",
            "application",
        ],
    )


@institutional_bp.route("/grants/applications/<int:application_id>/edit", methods=["GET", "POST"])
@admin_required
def grant_applications_edit(application_id: int):
    application = GrantApplication.query.get_or_404(application_id)
    if request.method == "POST":
        _populate_grant_application(application)
        if _commit_or_rollback("Grant application"):
            return redirect(url_for("institutional.grant_applications_detail", application_id=application.id))

    return render_template(
        "admin/institutional/grant_application_form.html",
        application=application,
        opportunities=_grant_opportunity_query().order_by(GrantOpportunity.title.asc()).all(),
        statuses=GRANT_APPLICATION_STATUSES,
        action="Update",
    )


def _populate_grant_application(application: GrantApplication) -> None:
    application.grant_opportunity_id = int(request.form.get("grant_opportunity_id"))
    application.title = _clean(request.form.get("title")) or "Untitled grant application"
    application.application_status = (
        request.form.get("application_status")
        if request.form.get("application_status") in GRANT_APPLICATION_STATUSES
        else "drafting"
    )
    application.submission_date = _parse_date(request.form.get("submission_date"))
    application.requested_amount = _parse_money(request.form.get("requested_amount"))
    application.awarded_amount = _parse_money(request.form.get("awarded_amount"))
    application.currency = _clean(request.form.get("currency")) or "USD"
    application.project_title = _clean(request.form.get("project_title"))
    application.summary = _clean(request.form.get("summary"))
    application.notes = _clean(request.form.get("notes"))
    application.internal_owner_user_id = application.internal_owner_user_id or _current_admin_id()


@institutional_bp.route("/grants/applications/<int:application_id>/milestones/new", methods=["GET", "POST"])
@admin_required
def grant_milestones_new(application_id: int):
    application = GrantApplication.query.get_or_404(application_id)
    milestone = GrantMilestone(grant_application_id=application.id)
    if request.method == "POST":
        _populate_grant_milestone(milestone)
        db.session.add(milestone)
        if _commit_or_rollback("Grant milestone"):
            return redirect(url_for("institutional.grant_applications_detail", application_id=application.id))
    return render_template(
        "admin/institutional/grant_milestone_form.html",
        application=application,
        milestone=milestone,
        statuses=GRANT_MILESTONE_STATUSES,
        action="Create",
    )


@institutional_bp.route("/grants/applications/<int:application_id>/milestones/<int:milestone_id>/edit", methods=["GET", "POST"])
@admin_required
def grant_milestones_edit(application_id: int, milestone_id: int):
    application = GrantApplication.query.get_or_404(application_id)
    milestone = GrantMilestone.query.filter_by(id=milestone_id, grant_application_id=application.id).first_or_404()
    if request.method == "POST":
        _populate_grant_milestone(milestone)
        if _commit_or_rollback("Grant milestone"):
            return redirect(url_for("institutional.grant_applications_detail", application_id=application.id))
    return render_template(
        "admin/institutional/grant_milestone_form.html",
        application=application,
        milestone=milestone,
        statuses=GRANT_MILESTONE_STATUSES,
        action="Update",
    )


def _populate_grant_milestone(milestone: GrantMilestone) -> None:
    milestone.title = _clean(request.form.get("title")) or "Untitled milestone"
    milestone.due_date = _parse_date(request.form.get("due_date"))
    milestone.status = request.form.get("status") if request.form.get("status") in GRANT_MILESTONE_STATUSES else "pending"
    milestone.description = _clean(request.form.get("description"))
    milestone.completion_notes = _clean(request.form.get("completion_notes"))


@institutional_bp.route("/grants/applications/<int:application_id>/reports/new", methods=["GET", "POST"])
@admin_required
def grant_reports_new(application_id: int):
    application = GrantApplication.query.get_or_404(application_id)
    report = GrantReport(grant_application_id=application.id)
    if request.method == "POST":
        _populate_grant_report(report)
        db.session.add(report)
        if _commit_or_rollback("Grant report"):
            return redirect(url_for("institutional.grant_applications_detail", application_id=application.id))
    return render_template(
        "admin/institutional/grant_report_form.html",
        application=application,
        report=report,
        report_types=GRANT_REPORT_TYPES,
        statuses=GRANT_REPORT_STATUSES,
        action="Create",
    )


@institutional_bp.route("/grants/applications/<int:application_id>/reports/<int:report_id>/edit", methods=["GET", "POST"])
@admin_required
def grant_reports_edit(application_id: int, report_id: int):
    application = GrantApplication.query.get_or_404(application_id)
    report = GrantReport.query.filter_by(id=report_id, grant_application_id=application.id).first_or_404()
    if request.method == "POST":
        _populate_grant_report(report)
        if _commit_or_rollback("Grant report"):
            return redirect(url_for("institutional.grant_applications_detail", application_id=application.id))
    return render_template(
        "admin/institutional/grant_report_form.html",
        application=application,
        report=report,
        report_types=GRANT_REPORT_TYPES,
        statuses=GRANT_REPORT_STATUSES,
        action="Update",
    )


def _populate_grant_report(report: GrantReport) -> None:
    report.report_type = request.form.get("report_type") if request.form.get("report_type") in GRANT_REPORT_TYPES else "narrative"
    report.reporting_period_start = _parse_date(request.form.get("reporting_period_start"))
    report.reporting_period_end = _parse_date(request.form.get("reporting_period_end"))
    report.due_date = _parse_date(request.form.get("due_date"))
    report.submitted_date = _parse_date(request.form.get("submitted_date"))
    report.status = request.form.get("status") if request.form.get("status") in GRANT_REPORT_STATUSES else "draft"
    report.summary = _clean(request.form.get("summary"))
    report.notes = _clean(request.form.get("notes"))


@institutional_bp.route("/grants/applications/<int:application_id>/impact-metrics/new", methods=["GET", "POST"])
@admin_required
def grant_impact_metrics_new(application_id: int):
    application = GrantApplication.query.get_or_404(application_id)
    metric = GrantImpactMetric(grant_application_id=application.id)
    if request.method == "POST":
        _populate_grant_impact_metric(metric)
        db.session.add(metric)
        if _commit_or_rollback("Grant impact metric"):
            return redirect(url_for("institutional.grant_applications_detail", application_id=application.id))
    return render_template(
        "admin/institutional/grant_impact_metric_form.html",
        application=application,
        metric=metric,
        metric_types=GRANT_IMPACT_METRIC_TYPES,
        statuses=GRANT_IMPACT_METRIC_STATUSES,
        metric_definitions=IMPACT_METRICS,
        action="Create",
    )


@institutional_bp.route("/grants/applications/<int:application_id>/impact-metrics/<int:metric_id>/edit", methods=["GET", "POST"])
@admin_required
def grant_impact_metrics_edit(application_id: int, metric_id: int):
    application = GrantApplication.query.get_or_404(application_id)
    metric = GrantImpactMetric.query.filter_by(id=metric_id, grant_application_id=application.id).first_or_404()
    if request.method == "POST":
        _populate_grant_impact_metric(metric)
        if _commit_or_rollback("Grant impact metric"):
            return redirect(url_for("institutional.grant_applications_detail", application_id=application.id))
    return render_template(
        "admin/institutional/grant_impact_metric_form.html",
        application=application,
        metric=metric,
        metric_types=GRANT_IMPACT_METRIC_TYPES,
        statuses=GRANT_IMPACT_METRIC_STATUSES,
        metric_definitions=IMPACT_METRICS,
        action="Update",
    )


def _populate_grant_impact_metric(metric: GrantImpactMetric) -> None:
    metric.name = _clean(request.form.get("name")) or "Untitled impact metric"
    metric.metric_code = _clean(request.form.get("metric_code"))
    if metric.metric_code not in IMPACT_METRICS:
        metric.metric_code = None
    metric.metric_type = (
        request.form.get("metric_type")
        if request.form.get("metric_type") in GRANT_IMPACT_METRIC_TYPES
        else "impact"
    )
    metric.unit = _clean(request.form.get("unit"))
    metric.baseline_value = _parse_money(request.form.get("baseline_value"))
    metric.target_value = _parse_money(request.form.get("target_value"))
    metric.current_value = _parse_money(request.form.get("current_value"))
    metric.reporting_period_start = _parse_date(request.form.get("reporting_period_start"))
    metric.reporting_period_end = _parse_date(request.form.get("reporting_period_end"))
    metric.status = (
        request.form.get("status")
        if request.form.get("status") in GRANT_IMPACT_METRIC_STATUSES
        else "planned"
    )
    metric.notes = _clean(request.form.get("notes"))


@institutional_bp.route("/grants/<int:opportunity_id>/documents/new", methods=["GET", "POST"])
@admin_required
def grant_opportunity_documents_new(opportunity_id: int):
    opportunity = GrantOpportunity.query.get_or_404(opportunity_id)
    document = GrantDocument(grant_opportunity_id=opportunity.id)
    if request.method == "POST":
        _populate_grant_document(document)
        document.grant_opportunity_id = opportunity.id
        document.grant_application_id = None
        db.session.add(document)
        if _commit_or_rollback("Grant document"):
            return redirect(url_for("institutional.grants_detail", opportunity_id=opportunity.id))
    return render_template(
        "admin/institutional/grant_document_form.html",
        opportunity=opportunity,
        application=None,
        document=document,
        document_types=GRANT_DOCUMENT_TYPES,
        action="Register",
    )


@institutional_bp.route("/grants/applications/<int:application_id>/documents/new", methods=["GET", "POST"])
@admin_required
def grant_application_documents_new(application_id: int):
    application = GrantApplication.query.get_or_404(application_id)
    document = GrantDocument(grant_application_id=application.id, grant_opportunity_id=application.grant_opportunity_id)
    if request.method == "POST":
        _populate_grant_document(document)
        document.grant_application_id = application.id
        document.grant_opportunity_id = application.grant_opportunity_id
        db.session.add(document)
        if _commit_or_rollback("Grant document"):
            return redirect(url_for("institutional.grant_applications_detail", application_id=application.id))
    return render_template(
        "admin/institutional/grant_document_form.html",
        opportunity=application.grant_opportunity,
        application=application,
        document=document,
        document_types=GRANT_DOCUMENT_TYPES,
        action="Register",
    )


def _populate_grant_document(document: GrantDocument) -> None:
    document.title = _clean(request.form.get("title")) or "Untitled grant document"
    document.document_type = (
        request.form.get("document_type")
        if request.form.get("document_type") in GRANT_DOCUMENT_TYPES
        else "other"
    )
    document.file_path = _clean(request.form.get("file_path"))
    document.external_url = _clean(request.form.get("external_url"))
    document.notes = _clean(request.form.get("notes"))


@institutional_bp.route("/evidence/new", methods=["GET", "POST"])
@admin_required
def evidence_new():
    evidence = EvidenceRecord()
    evidence.linked_model_type = _clean(request.args.get("linked_model_type")) or ""
    linked_model_id = _clean(request.args.get("linked_model_id"))
    evidence.linked_model_id = int(linked_model_id) if linked_model_id else None
    next_url = _clean(request.args.get("next")) or url_for("institutional.impact_dashboard")

    if request.method == "POST":
        _populate_evidence_record(evidence)
        db.session.add(evidence)
        if _commit_or_rollback("Evidence record"):
            return redirect(request.form.get("next") or next_url)

    return render_template(
        "admin/institutional/evidence_form.html",
        evidence=evidence,
        evidence_types=EVIDENCE_TYPES,
        link_types=EVIDENCE_LINK_TYPES,
        next_url=next_url,
        action="Register",
    )


def _populate_evidence_record(evidence: EvidenceRecord) -> None:
    evidence.linked_model_type = _clean(request.form.get("linked_model_type")) or "GrantReport"
    if evidence.linked_model_type not in EVIDENCE_LINK_TYPES:
        evidence.linked_model_type = "GrantReport"
    evidence.linked_model_id = int(request.form.get("linked_model_id"))
    evidence.title = _clean(request.form.get("title")) or "Untitled evidence"
    evidence.description = _clean(request.form.get("description"))
    evidence.evidence_type = (
        request.form.get("evidence_type") if request.form.get("evidence_type") in EVIDENCE_TYPES else "other"
    )
    evidence.file_path = _clean(request.form.get("file_path"))
    evidence.external_url = _clean(request.form.get("external_url"))
    evidence.county = _clean(request.form.get("county"))
    evidence.captured_on = _parse_date(request.form.get("captured_on"))


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
