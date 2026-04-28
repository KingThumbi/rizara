# app/routes/procurement.py
from __future__ import annotations

from datetime import date
from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import (
    AggregationBatch,
    ProcurementRecord,
    ProcurementSource,
)

bp = Blueprint("procurement", __name__, url_prefix="/procurement")


@bp.get("/")
@login_required
def dashboard():
    sources_count = ProcurementSource.query.count()
    records_count = ProcurementRecord.query.count()

    recent_records = (
        ProcurementRecord.query
        .order_by(ProcurementRecord.created_at.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "procurement/dashboard.html",
        sources_count=sources_count,
        records_count=records_count,
        recent_records=recent_records,
    )


@bp.get("/sources")
@login_required
def sources_list():
    source_type = request.args.get("source_type", "").strip()

    query = ProcurementSource.query.order_by(ProcurementSource.name.asc())

    if source_type in {"farmer", "market"}:
        query = query.filter(ProcurementSource.source_type == source_type)

    sources = query.all()

    return render_template(
        "procurement/sources_list.html",
        sources=sources,
        source_type=source_type,
    )


@bp.route("/sources/new", methods=["GET", "POST"])
@login_required
def source_new():
    if request.method == "POST":
        source_type = request.form.get("source_type", "").strip()
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip() or None
        location = request.form.get("location", "").strip() or None
        county = request.form.get("county", "").strip() or None
        notes = request.form.get("notes", "").strip() or None

        if source_type not in {"farmer", "market"}:
            flash("Source type must be farmer or market.", "error")
            return redirect(url_for("procurement.source_new"))

        if not name:
            flash("Source name is required.", "error")
            return redirect(url_for("procurement.source_new"))

        source = ProcurementSource(
            source_type=source_type,
            name=name,
            phone=phone,
            location=location,
            county=county,
            notes=notes,
            is_active=True,
        )

        db.session.add(source)
        db.session.commit()

        flash("Procurement source created successfully.", "success")
        return redirect(url_for("procurement.sources_list"))

    return render_template("procurement/source_form.html")


@bp.get("/records")
@login_required
def records_list():
    status = request.args.get("status", "").strip()
    animal_type = request.args.get("animal_type", "").strip()
    source_type = request.args.get("source_type", "").strip()

    query = ProcurementRecord.query.join(ProcurementSource)

    if status:
        query = query.filter(ProcurementRecord.status == status)

    if animal_type in {"goat", "sheep", "cattle"}:
        query = query.filter(ProcurementRecord.animal_type == animal_type)

    if source_type in {"farmer", "market"}:
        query = query.filter(ProcurementSource.source_type == source_type)

    records = query.order_by(ProcurementRecord.created_at.desc()).all()

    return render_template(
        "procurement/records_list.html",
        records=records,
        status=status,
        animal_type=animal_type,
        source_type=source_type,
    )


@bp.route("/records/new", methods=["GET", "POST"])
@login_required
def record_new():
    sources = (
        ProcurementSource.query
        .filter_by(is_active=True)
        .order_by(ProcurementSource.source_type.asc(), ProcurementSource.name.asc())
        .all()
    )

    batches = (
        AggregationBatch.query
        .filter_by(is_locked=False)
        .order_by(AggregationBatch.created_at.desc())
        .all()
    )

    if request.method == "POST":
        source_id = request.form.get("source_id", type=int)
        aggregation_batch_id = request.form.get("aggregation_batch_id", type=int)
        animal_type = request.form.get("animal_type", "").strip()
        quantity = request.form.get("quantity", type=int) or 0
        unit_price = Decimal(request.form.get("unit_price") or "0")
        total_cost = Decimal(request.form.get("total_cost") or "0")
        estimated_total_weight_kg = Decimal(request.form.get("estimated_total_weight_kg") or "0")
        purchase_date_raw = request.form.get("purchase_date", "").strip()
        reference = request.form.get("reference", "").strip() or None
        notes = request.form.get("notes", "").strip() or None

        source = ProcurementSource.query.get(source_id)
        batch = AggregationBatch.query.get(aggregation_batch_id) if aggregation_batch_id else None
        if not source:
            flash("Select a valid farmer or market.", "error")
            return redirect(url_for("procurement.record_new"))

        if animal_type not in {"goat", "sheep", "cattle"}:
            flash("Animal type must be goat, sheep, or cattle.", "error")
            return redirect(url_for("procurement.record_new"))

        if quantity <= 0:
            flash("Quantity must be greater than zero.", "error")
            return redirect(url_for("procurement.record_new"))

        if batch and batch.animal_type != animal_type:
            flash("Selected batch animal type does not match procurement animal type.", "error")
            return redirect(url_for("procurement.record_new"))

        purchase_date = date.fromisoformat(purchase_date_raw) if purchase_date_raw else date.today()

        if total_cost <= 0 and unit_price > 0:
            total_cost = unit_price * quantity

        estimated_avg_weight_kg = (
            estimated_total_weight_kg / quantity
            if quantity and estimated_total_weight_kg
            else Decimal("0")
        )

        record = ProcurementRecord(
            source_id=source.id,
            aggregation_batch_id=batch.id if batch else None,
            animal_type=animal_type,
            quantity=quantity,
            unit_price=unit_price,
            total_cost=total_cost,
            estimated_total_weight_kg=estimated_total_weight_kg,
            estimated_avg_weight_kg=estimated_avg_weight_kg,
            purchase_date=purchase_date,
            status="confirmed",
            reference=reference,
            notes=notes,
        )

        db.session.add(record)
        db.session.commit()

        flash("Procurement record created successfully.", "success")
        return redirect(url_for("procurement.record_detail", record_id=record.id))

    return render_template(
        "procurement/record_form.html",
        sources=sources,
        batches=batches,
    )


@bp.get("/records/<int:record_id>")
@login_required
def record_detail(record_id: int):
    record = ProcurementRecord.query.get_or_404(record_id)

    return render_template(
        "procurement/record_detail.html",
        record=record,
    )


@bp.post("/records/<int:record_id>/generate-animals")
@login_required
def generate_animals(record_id: int):
    record = ProcurementRecord.query.get_or_404(record_id)

    try:
        created_animals = record.generate_animals()
        db.session.commit()

        flash(
            f"{len(created_animals)} {record.animal_type}(s) generated and attached to aggregation batch.",
            "success",
        )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    except Exception as exc:
        db.session.rollback()
        flash(f"Could not generate animals: {exc}", "error")

    return redirect(url_for("procurement.record_detail", record_id=record.id))