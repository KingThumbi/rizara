from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

import sqlalchemy as sa
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.models import Farmer, FieldLivestockIntake, Stakeholder, StakeholderActivity
from app.utils.guards import admin_required


kaewa_bp = Blueprint("kaewa", __name__, url_prefix="/admin/kaewa")

STAKEHOLDER_CATEGORIES = [
    "farmer",
    "vet",
    "transporter",
    "feed_supplier",
    "aggregation_agent",
    "butcher",
    "buyer",
    "other",
]
STAKEHOLDER_STATUSES = ["active", "pending_verification", "suspended", "inactive"]
STAKEHOLDER_ACTIVITY_TYPES = ["note", "call", "visit", "training", "verification", "liaison", "other"]
INTAKE_ANIMAL_TYPES = ["goat", "sheep", "cattle"]
INTAKE_STATUSES = ["draft", "pending_verification", "accepted", "rejected", "transferred_to_aggregation"]


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _parse_date(value: str | None) -> date | None:
    value = _clean(value)
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_decimal(value: str | None) -> Decimal | None:
    value = _clean(value)
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _parse_int(value: str | None, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _current_admin_id() -> int | None:
    return getattr(current_user, "id", None) if getattr(current_user, "is_authenticated", False) else None


def _commit_or_rollback(action: str) -> bool:
    try:
        db.session.commit()
        flash(f"{action} saved.", "success")
        return True
    except Exception as exc:
        db.session.rollback()
        flash(f"{action} failed: {exc}", "danger")
        return False


@kaewa_bp.route("", methods=["GET"])
@admin_required
def dashboard():
    stakeholder_counts = dict(
        db.session.query(Stakeholder.category, sa.func.count(Stakeholder.id))
        .group_by(Stakeholder.category)
        .all()
    )
    pending_statuses = ["pending_verification", "draft"]
    stats = {
        "registered_stakeholders": Stakeholder.query.count(),
        "farmers": stakeholder_counts.get("farmer", 0) + Farmer.query.count(),
        "service_providers": sum(
            stakeholder_counts.get(category, 0)
            for category in ("vet", "transporter", "feed_supplier")
        ),
        "aggregation_agents": stakeholder_counts.get("aggregation_agent", 0),
        "livestock_intake_records": FieldLivestockIntake.query.count(),
        "pending_verification_records": Stakeholder.query.filter(
            Stakeholder.status == "pending_verification"
        ).count()
        + FieldLivestockIntake.query.filter(FieldLivestockIntake.intake_status.in_(pending_statuses)).count(),
    }
    recent_activities = StakeholderActivity.query.order_by(StakeholderActivity.created_at.desc()).limit(8).all()
    recent_intakes = FieldLivestockIntake.query.order_by(FieldLivestockIntake.created_at.desc()).limit(6).all()
    return render_template(
        "admin/kaewa/dashboard.html",
        stats=stats,
        recent_activities=recent_activities,
        recent_intakes=recent_intakes,
    )


@kaewa_bp.route("/stakeholders", methods=["GET"])
@admin_required
def stakeholders_index():
    filters = {
        "category": _clean(request.args.get("category")),
        "status": _clean(request.args.get("status")),
        "county": _clean(request.args.get("county")),
        "sub_county": _clean(request.args.get("sub_county")),
    }
    query = Stakeholder.query
    if filters["category"] in STAKEHOLDER_CATEGORIES:
        query = query.filter(Stakeholder.category == filters["category"])
    if filters["status"] in STAKEHOLDER_STATUSES:
        query = query.filter(Stakeholder.status == filters["status"])
    if filters["county"]:
        query = query.filter(Stakeholder.county.ilike(f"%{filters['county']}%"))
    if filters["sub_county"]:
        query = query.filter(Stakeholder.sub_county.ilike(f"%{filters['sub_county']}%"))
    stakeholders = query.order_by(Stakeholder.created_at.desc()).limit(200).all()
    return render_template(
        "admin/kaewa/stakeholders_index.html",
        stakeholders=stakeholders,
        categories=STAKEHOLDER_CATEGORIES,
        statuses=STAKEHOLDER_STATUSES,
        filters=filters,
    )


@kaewa_bp.route("/stakeholders/new", methods=["GET", "POST"])
@admin_required
def stakeholders_new():
    stakeholder = Stakeholder(created_by_user_id=_current_admin_id())
    if request.method == "POST":
        _populate_stakeholder(stakeholder)
        db.session.add(stakeholder)
        if _commit_or_rollback("Stakeholder"):
            return redirect(url_for("kaewa.stakeholders_detail", stakeholder_id=stakeholder.id))
    return render_template(
        "admin/kaewa/stakeholder_form.html",
        stakeholder=stakeholder,
        categories=STAKEHOLDER_CATEGORIES,
        statuses=STAKEHOLDER_STATUSES,
        action="Create",
    )


@kaewa_bp.route("/stakeholders/<int:stakeholder_id>", methods=["GET"])
@admin_required
def stakeholders_detail(stakeholder_id: int):
    stakeholder = Stakeholder.query.get_or_404(stakeholder_id)
    intakes = FieldLivestockIntake.query.filter_by(stakeholder_id=stakeholder.id).order_by(
        FieldLivestockIntake.created_at.desc()
    ).all()
    return render_template(
        "admin/kaewa/stakeholder_detail.html",
        stakeholder=stakeholder,
        activities=stakeholder.activities,
        documents=stakeholder.documents,
        intakes=intakes,
        activity_types=STAKEHOLDER_ACTIVITY_TYPES,
    )


@kaewa_bp.route("/stakeholders/<int:stakeholder_id>/edit", methods=["GET", "POST"])
@admin_required
def stakeholders_edit(stakeholder_id: int):
    stakeholder = Stakeholder.query.get_or_404(stakeholder_id)
    if request.method == "POST":
        _populate_stakeholder(stakeholder)
        if _commit_or_rollback("Stakeholder"):
            return redirect(url_for("kaewa.stakeholders_detail", stakeholder_id=stakeholder.id))
    return render_template(
        "admin/kaewa/stakeholder_form.html",
        stakeholder=stakeholder,
        categories=STAKEHOLDER_CATEGORIES,
        statuses=STAKEHOLDER_STATUSES,
        action="Update",
    )


@kaewa_bp.route("/stakeholders/<int:stakeholder_id>/activities/new", methods=["POST"])
@admin_required
def stakeholder_activities_new(stakeholder_id: int):
    stakeholder = Stakeholder.query.get_or_404(stakeholder_id)
    activity = StakeholderActivity(
        stakeholder_id=stakeholder.id,
        created_by_user_id=_current_admin_id(),
    )
    activity.activity_type = (
        request.form.get("activity_type")
        if request.form.get("activity_type") in STAKEHOLDER_ACTIVITY_TYPES
        else "note"
    )
    activity.subject = _clean(request.form.get("subject"))
    activity.notes = _clean(request.form.get("notes"))
    activity.activity_date = _parse_date(request.form.get("activity_date"))
    db.session.add(activity)
    _commit_or_rollback("Stakeholder activity")
    return redirect(url_for("kaewa.stakeholders_detail", stakeholder_id=stakeholder.id))


def _populate_stakeholder(stakeholder: Stakeholder) -> None:
    stakeholder.name = _clean(request.form.get("name")) or "Unnamed stakeholder"
    stakeholder.phone = _clean(request.form.get("phone")) or "Not provided"
    stakeholder.email = _clean(request.form.get("email"))
    stakeholder.category = (
        request.form.get("category") if request.form.get("category") in STAKEHOLDER_CATEGORIES else "other"
    )
    stakeholder.county = _clean(request.form.get("county"))
    stakeholder.sub_county = _clean(request.form.get("sub_county"))
    stakeholder.ward = _clean(request.form.get("ward"))
    stakeholder.village = _clean(request.form.get("village"))
    stakeholder.national_id = _clean(request.form.get("national_id"))
    stakeholder.notes = _clean(request.form.get("notes"))
    stakeholder.status = (
        request.form.get("status") if request.form.get("status") in STAKEHOLDER_STATUSES else "pending_verification"
    )
    stakeholder.created_by_user_id = stakeholder.created_by_user_id or _current_admin_id()


@kaewa_bp.route("/intakes", methods=["GET"])
@admin_required
def intakes_index():
    status = _clean(request.args.get("status"))
    animal_type = _clean(request.args.get("animal_type"))
    query = FieldLivestockIntake.query
    if status in INTAKE_STATUSES:
        query = query.filter(FieldLivestockIntake.intake_status == status)
    if animal_type in INTAKE_ANIMAL_TYPES:
        query = query.filter(FieldLivestockIntake.animal_type == animal_type)
    intakes = query.order_by(FieldLivestockIntake.created_at.desc()).limit(200).all()
    return render_template(
        "admin/kaewa/intakes_index.html",
        intakes=intakes,
        statuses=INTAKE_STATUSES,
        animal_types=INTAKE_ANIMAL_TYPES,
        filters={"status": status, "animal_type": animal_type},
    )


@kaewa_bp.route("/intakes/new", methods=["GET", "POST"])
@admin_required
def intakes_new():
    intake = FieldLivestockIntake(office_location="Kaewa", created_by_user_id=_current_admin_id())
    stakeholder_id = _parse_int(request.args.get("stakeholder_id"), 0)
    intake.stakeholder_id = stakeholder_id or None
    stakeholders = Stakeholder.query.order_by(Stakeholder.name.asc()).limit(300).all()
    if request.method == "POST":
        _populate_intake(intake)
        db.session.add(intake)
        if _commit_or_rollback("Livestock intake"):
            return redirect(url_for("kaewa.intakes_detail", intake_id=intake.id))
    return render_template(
        "admin/kaewa/intake_form.html",
        intake=intake,
        stakeholders=stakeholders,
        animal_types=INTAKE_ANIMAL_TYPES,
        statuses=INTAKE_STATUSES,
        action="Create",
    )


@kaewa_bp.route("/intakes/<int:intake_id>", methods=["GET"])
@admin_required
def intakes_detail(intake_id: int):
    intake = FieldLivestockIntake.query.get_or_404(intake_id)
    return render_template("admin/kaewa/intake_detail.html", intake=intake, statuses=INTAKE_STATUSES)


@kaewa_bp.route("/intakes/<int:intake_id>/edit", methods=["GET", "POST"])
@admin_required
def intakes_edit(intake_id: int):
    intake = FieldLivestockIntake.query.get_or_404(intake_id)
    stakeholders = Stakeholder.query.order_by(Stakeholder.name.asc()).limit(300).all()
    if request.method == "POST":
        _populate_intake(intake)
        if _commit_or_rollback("Livestock intake"):
            return redirect(url_for("kaewa.intakes_detail", intake_id=intake.id))
    return render_template(
        "admin/kaewa/intake_form.html",
        intake=intake,
        stakeholders=stakeholders,
        animal_types=INTAKE_ANIMAL_TYPES,
        statuses=INTAKE_STATUSES,
        action="Update",
    )


@kaewa_bp.route("/intakes/<int:intake_id>/status", methods=["POST"])
@admin_required
def intakes_status_update(intake_id: int):
    intake = FieldLivestockIntake.query.get_or_404(intake_id)
    status = request.form.get("intake_status")
    intake.intake_status = status if status in INTAKE_STATUSES else intake.intake_status
    _commit_or_rollback("Livestock intake status")
    return redirect(url_for("kaewa.intakes_detail", intake_id=intake.id))


def _populate_intake(intake: FieldLivestockIntake) -> None:
    stakeholder_id = _parse_int(request.form.get("stakeholder_id"), 0)
    intake.stakeholder_id = stakeholder_id or None
    intake.office_location = _clean(request.form.get("office_location")) or "Kaewa"
    intake.animal_type = (
        request.form.get("animal_type") if request.form.get("animal_type") in INTAKE_ANIMAL_TYPES else "goat"
    )
    intake.count = max(_parse_int(request.form.get("count"), 0), 0)
    intake.estimated_total_weight_kg = _parse_decimal(request.form.get("estimated_total_weight_kg"))
    intake.source_location = _clean(request.form.get("source_location"))
    intake.intake_status = (
        request.form.get("intake_status") if request.form.get("intake_status") in INTAKE_STATUSES else "draft"
    )
    intake.notes = _clean(request.form.get("notes"))
    intake.created_by_user_id = intake.created_by_user_id or _current_admin_id()
