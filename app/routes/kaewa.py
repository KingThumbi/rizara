from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

import sqlalchemy as sa
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.models import (
    AggregationBatch,
    Farmer,
    FieldLivestockIntake,
    FieldLivestockIntakeActivity,
    HoldingPen,
    HoldingPenActivity,
    HoldingPenAssignment,
    KaewaDailyReconciliation,
    KaewaDailyReconciliationLine,
    RuralServiceProduct,
    RuralServiceSale,
    RuralServiceSaleItem,
    RuralServiceStockMovement,
    Stakeholder,
    StakeholderActivity,
    utcnow_naive,
)
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
HANDOFF_STATUSES = ["none", "ready_for_aggregation", "handed_off", "cancelled"]
HOLDING_PEN_ANIMAL_TYPES = ["goat", "sheep", "cattle", "mixed"]
HOLDING_PEN_STATUSES = ["active", "inactive", "maintenance"]
HOLDING_ASSIGNMENT_STATUSES = ["active", "released"]
HOLDING_RELEASE_REASONS = ["transferred_to_aggregation", "rejected", "sold", "dead_loss", "other"]
HOLDING_ACTIVITY_TYPES = ["assignment", "release", "feeding", "treatment", "inspection", "mortality", "note"]
RURAL_PRODUCT_CATEGORIES = [
    "animal_feed",
    "mineral_supplement",
    "farm_tool",
    "livestock_equipment",
    "veterinary_basic",
    "rizara_merchandise",
    "other",
]
RURAL_PRODUCT_UNITS = ["bag", "kg", "litre", "piece", "packet", "bale", "other"]
RURAL_STOCK_IN_TYPES = {"opening_stock", "purchase", "adjustment_in", "sale_reversal"}
RURAL_STOCK_OUT_TYPES = {"adjustment_out", "damaged", "expired", "issued_internal", "sale"}
RURAL_STOCK_MOVEMENT_TYPES = [
    "opening_stock",
    "purchase",
    "adjustment_in",
    "adjustment_out",
    "damaged",
    "expired",
    "issued_internal",
    "sale",
    "sale_reversal",
]
RURAL_SALE_PAYMENT_METHODS = ["cash", "mpesa", "bank", "credit", "internal"]
RURAL_SALE_STATUSES = ["draft", "completed", "cancelled"]
KAEWA_RECONCILIATION_STATUSES = ["draft", "submitted", "reviewed"]


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _parse_date(value: str | None) -> date | None:
    value = _clean(value)
    if not value:
        return None
    return date.fromisoformat(value)


def _day_bounds(value: date) -> tuple[datetime, datetime]:
    start = datetime.combine(value, time.min)
    return start, start + timedelta(days=1)


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


def _record_intake_activity(
    intake: FieldLivestockIntake,
    event_type: str,
    from_status: str | None,
    to_status: str | None,
    notes: str | None = None,
) -> None:
    db.session.add(
        FieldLivestockIntakeActivity(
            intake_id=intake.id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            notes=notes,
            created_by_user_id=_current_admin_id(),
        )
    )


def _holding_pen_occupancy(pen: HoldingPen) -> int:
    return (
        db.session.query(sa.func.coalesce(sa.func.sum(HoldingPenAssignment.count), 0))
        .filter(
            HoldingPenAssignment.holding_pen_id == pen.id,
            HoldingPenAssignment.status == "active",
        )
        .scalar()
        or 0
    )


def _holding_pen_capacity_remaining(pen: HoldingPen) -> int | None:
    if pen.capacity_count is None:
        return None
    return pen.capacity_count - _holding_pen_occupancy(pen)


def _holding_pen_summary(pen: HoldingPen) -> dict:
    occupancy = _holding_pen_occupancy(pen)
    utilization = None
    if pen.capacity_count:
        utilization = round((occupancy / pen.capacity_count) * 100)
    return {"pen": pen, "occupancy": occupancy, "utilization": utilization}


def _record_holding_pen_activity(
    pen: HoldingPen,
    activity_type: str,
    description: str | None,
    assignment_id: int | None = None,
) -> None:
    db.session.add(
        HoldingPenActivity(
            holding_pen_id=pen.id,
            holding_pen_assignment_id=assignment_id,
            activity_type=activity_type if activity_type in HOLDING_ACTIVITY_TYPES else "note",
            description=description,
            created_by_user_id=_current_admin_id(),
        )
    )


def _product_stock_balance(product: RuralServiceProduct) -> Decimal:
    total_in = (
        db.session.query(sa.func.coalesce(sa.func.sum(RuralServiceStockMovement.quantity), 0))
        .filter(
            RuralServiceStockMovement.product_id == product.id,
            RuralServiceStockMovement.movement_type.in_(RURAL_STOCK_IN_TYPES),
        )
        .scalar()
        or Decimal("0")
    )
    total_out = (
        db.session.query(sa.func.coalesce(sa.func.sum(RuralServiceStockMovement.quantity), 0))
        .filter(
            RuralServiceStockMovement.product_id == product.id,
            RuralServiceStockMovement.movement_type.in_(RURAL_STOCK_OUT_TYPES),
        )
        .scalar()
        or Decimal("0")
    )
    return Decimal(total_in) - Decimal(total_out)


def _product_stock_balance_as_of(product: RuralServiceProduct, as_of_date: date) -> Decimal:
    _, end = _day_bounds(as_of_date)
    total_in = (
        db.session.query(sa.func.coalesce(sa.func.sum(RuralServiceStockMovement.quantity), 0))
        .filter(
            RuralServiceStockMovement.product_id == product.id,
            RuralServiceStockMovement.movement_type.in_(RURAL_STOCK_IN_TYPES),
            RuralServiceStockMovement.created_at < end,
        )
        .scalar()
        or Decimal("0")
    )
    total_out = (
        db.session.query(sa.func.coalesce(sa.func.sum(RuralServiceStockMovement.quantity), 0))
        .filter(
            RuralServiceStockMovement.product_id == product.id,
            RuralServiceStockMovement.movement_type.in_(RURAL_STOCK_OUT_TYPES),
            RuralServiceStockMovement.created_at < end,
        )
        .scalar()
        or Decimal("0")
    )
    return Decimal(total_in) - Decimal(total_out)


def _product_summary(product: RuralServiceProduct) -> dict:
    stock = _product_stock_balance(product)
    low_stock = product.reorder_level is not None and stock <= product.reorder_level
    return {"product": product, "stock": stock, "low_stock": low_stock}


def _next_rural_sale_number() -> str:
    return f"KRS-{utcnow_naive().strftime('%Y%m%d%H%M%S%f')}"


def _sale_total(sale: RuralServiceSale) -> Decimal:
    return sum((Decimal(item.line_total or 0) for item in sale.items), Decimal("0"))


def _completed_sales_query(start_date: date | None = None, end_date: date | None = None, payment_method: str | None = None):
    query = RuralServiceSale.query.filter(RuralServiceSale.status == "completed")
    if start_date:
        query = query.filter(RuralServiceSale.sale_date >= start_date)
    if end_date:
        query = query.filter(RuralServiceSale.sale_date <= end_date)
    if payment_method in RURAL_SALE_PAYMENT_METHODS:
        query = query.filter(RuralServiceSale.payment_method == payment_method)
    return query


def _completed_sales_totals_by_method(target_date: date | None = None) -> dict[str, Decimal]:
    query = _completed_sales_query(target_date, target_date) if target_date else _completed_sales_query()
    totals = {method: Decimal("0") for method in RURAL_SALE_PAYMENT_METHODS}
    for sale in query.all():
        totals[sale.payment_method] = totals.get(sale.payment_method, Decimal("0")) + _sale_total(sale)
    return totals


def _stock_report_summaries() -> list[dict]:
    summaries = []
    for product in RuralServiceProduct.query.order_by(RuralServiceProduct.name.asc()).all():
        summary = _product_summary(product)
        movement_count = RuralServiceStockMovement.query.filter_by(product_id=product.id).count()
        summaries.append({**summary, "movement_count": movement_count})
    return summaries


def _recalculate_reconciliation(reconciliation: KaewaDailyReconciliation) -> None:
    opening_cash = Decimal(reconciliation.opening_cash or 0)
    cash_total = Decimal(reconciliation.cash_sales_total or 0)
    reconciliation.expected_cash_total = opening_cash + cash_total
    if reconciliation.counted_cash is not None:
        reconciliation.cash_variance = Decimal(reconciliation.counted_cash) - Decimal(reconciliation.expected_cash_total or 0)
    else:
        reconciliation.cash_variance = None
    for line in reconciliation.lines:
        if line.counted_stock_qty is not None:
            line.variance_qty = Decimal(line.counted_stock_qty) - Decimal(line.system_stock_qty or 0)
        else:
            line.variance_qty = None


def _apply_reconciliation_sales_totals(reconciliation: KaewaDailyReconciliation) -> None:
    totals = _completed_sales_totals_by_method(reconciliation.reconciliation_date)
    reconciliation.cash_sales_total = totals["cash"]
    reconciliation.mpesa_sales_total = totals["mpesa"]
    reconciliation.bank_sales_total = totals["bank"]
    reconciliation.credit_sales_total = totals["credit"]
    reconciliation.internal_sales_total = totals["internal"]
    _recalculate_reconciliation(reconciliation)


def _snapshot_reconciliation_lines(reconciliation: KaewaDailyReconciliation) -> None:
    for product in RuralServiceProduct.query.order_by(RuralServiceProduct.name.asc()).all():
        reconciliation.lines.append(
            KaewaDailyReconciliationLine(
                product_id=product.id,
                system_stock_qty=_product_stock_balance_as_of(product, reconciliation.reconciliation_date),
            )
        )


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
        "holding_pens": HoldingPen.query.count(),
        "holding_occupancy": db.session.query(sa.func.coalesce(sa.func.sum(HoldingPenAssignment.count), 0))
        .filter(HoldingPenAssignment.status == "active")
        .scalar()
        or 0,
        "rural_service_products": RuralServiceProduct.query.count(),
        "low_stock_products": sum(
            1 for product in RuralServiceProduct.query.filter_by(active=True).all() if _product_summary(product)["low_stock"]
        ),
    }
    recent_activities = StakeholderActivity.query.order_by(StakeholderActivity.created_at.desc()).limit(8).all()
    recent_intakes = FieldLivestockIntake.query.order_by(FieldLivestockIntake.created_at.desc()).limit(6).all()
    holding_pen_summaries = [
        _holding_pen_summary(pen)
        for pen in HoldingPen.query.order_by(HoldingPen.status.asc(), HoldingPen.name.asc()).limit(6).all()
    ]
    rural_product_summaries = [
        _product_summary(product)
        for product in RuralServiceProduct.query.order_by(RuralServiceProduct.name.asc()).limit(6).all()
    ]
    return render_template(
        "admin/kaewa/dashboard.html",
        stats=stats,
        recent_activities=recent_activities,
        recent_intakes=recent_intakes,
        holding_pen_summaries=holding_pen_summaries,
        rural_product_summaries=rural_product_summaries,
    )


@kaewa_bp.route("/reports", methods=["GET"])
@admin_required
def reports_index():
    return render_template("admin/kaewa/reports_index.html")


@kaewa_bp.route("/reports/daily", methods=["GET"])
@admin_required
def reports_daily():
    report_date = _parse_date(request.args.get("date")) or date.today()
    start_dt, end_dt = _day_bounds(report_date)
    stakeholder_count = Stakeholder.query.filter(
        Stakeholder.created_at >= start_dt,
        Stakeholder.created_at < end_dt,
    ).count()
    intakes = FieldLivestockIntake.query.filter(
        FieldLivestockIntake.created_at >= start_dt,
        FieldLivestockIntake.created_at < end_dt,
    ).all()
    animal_counts = {animal_type: 0 for animal_type in INTAKE_ANIMAL_TYPES}
    for intake in intakes:
        animal_counts[intake.animal_type] = animal_counts.get(intake.animal_type, 0) + (intake.count or 0)
    stock_movements = RuralServiceStockMovement.query.filter(
        RuralServiceStockMovement.created_at >= start_dt,
        RuralServiceStockMovement.created_at < end_dt,
    ).order_by(RuralServiceStockMovement.created_at.desc()).all()
    low_stock_products = [summary for summary in _stock_report_summaries() if summary["low_stock"]]
    holding_pen_summaries = [
        _holding_pen_summary(pen)
        for pen in HoldingPen.query.order_by(HoldingPen.status.asc(), HoldingPen.name.asc()).all()
    ]
    return render_template(
        "admin/kaewa/report_daily.html",
        report_date=report_date,
        stakeholder_count=stakeholder_count,
        intakes=intakes,
        animal_counts=animal_counts,
        holding_pen_summaries=holding_pen_summaries,
        sales_totals=_completed_sales_totals_by_method(report_date),
        stock_movements=stock_movements,
        low_stock_products=low_stock_products,
    )


@kaewa_bp.route("/reports/stock", methods=["GET"])
@admin_required
def reports_stock():
    return render_template(
        "admin/kaewa/report_stock.html",
        product_summaries=_stock_report_summaries(),
    )


@kaewa_bp.route("/reports/sales", methods=["GET"])
@admin_required
def reports_sales():
    filters = {
        "start_date": _parse_date(request.args.get("start_date")),
        "end_date": _parse_date(request.args.get("end_date")),
        "payment_method": _clean(request.args.get("payment_method")),
    }
    sales = (
        _completed_sales_query(filters["start_date"], filters["end_date"], filters["payment_method"])
        .order_by(RuralServiceSale.sale_date.desc(), RuralServiceSale.created_at.desc())
        .limit(500)
        .all()
    )
    totals = {method: Decimal("0") for method in RURAL_SALE_PAYMENT_METHODS}
    grand_total = Decimal("0")
    for sale in sales:
        total = _sale_total(sale)
        totals[sale.payment_method] = totals.get(sale.payment_method, Decimal("0")) + total
        grand_total += total
    return render_template(
        "admin/kaewa/report_sales.html",
        sales=sales,
        totals=totals,
        grand_total=grand_total,
        payment_methods=RURAL_SALE_PAYMENT_METHODS,
        filters=filters,
    )


@kaewa_bp.route("/reports/intakes", methods=["GET"])
@admin_required
def reports_intakes():
    filters = {
        "start_date": _parse_date(request.args.get("start_date")),
        "end_date": _parse_date(request.args.get("end_date")),
        "animal_type": _clean(request.args.get("animal_type")),
        "status": _clean(request.args.get("status")),
    }
    query = FieldLivestockIntake.query
    if filters["start_date"]:
        query = query.filter(FieldLivestockIntake.created_at >= datetime.combine(filters["start_date"], time.min))
    if filters["end_date"]:
        query = query.filter(FieldLivestockIntake.created_at < datetime.combine(filters["end_date"] + timedelta(days=1), time.min))
    if filters["animal_type"] in INTAKE_ANIMAL_TYPES:
        query = query.filter(FieldLivestockIntake.animal_type == filters["animal_type"])
    if filters["status"] in INTAKE_STATUSES:
        query = query.filter(FieldLivestockIntake.intake_status == filters["status"])
    intakes = query.order_by(FieldLivestockIntake.created_at.desc()).limit(500).all()
    animal_counts = {animal_type: 0 for animal_type in INTAKE_ANIMAL_TYPES}
    for intake in intakes:
        animal_counts[intake.animal_type] = animal_counts.get(intake.animal_type, 0) + (intake.count or 0)
    return render_template(
        "admin/kaewa/report_intakes.html",
        intakes=intakes,
        animal_counts=animal_counts,
        filters=filters,
        animal_types=INTAKE_ANIMAL_TYPES,
        statuses=INTAKE_STATUSES,
    )


@kaewa_bp.route("/reports/stakeholders", methods=["GET"])
@admin_required
def reports_stakeholders():
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
    stakeholders = query.order_by(Stakeholder.created_at.desc()).limit(500).all()
    return render_template(
        "admin/kaewa/report_stakeholders.html",
        stakeholders=stakeholders,
        filters=filters,
        categories=STAKEHOLDER_CATEGORIES,
        statuses=STAKEHOLDER_STATUSES,
    )


@kaewa_bp.route("/reconciliations", methods=["GET"])
@admin_required
def reconciliations_index():
    reconciliations = KaewaDailyReconciliation.query.order_by(
        KaewaDailyReconciliation.reconciliation_date.desc()
    ).limit(200).all()
    return render_template(
        "admin/kaewa/reconciliations_index.html",
        reconciliations=reconciliations,
    )


@kaewa_bp.route("/reconciliations/new", methods=["GET", "POST"])
@admin_required
def reconciliations_new():
    reconciliation = KaewaDailyReconciliation(
        reconciliation_date=date.today(),
        office_location="Kaewa",
        status="draft",
        prepared_by_user_id=_current_admin_id(),
    )
    if request.method == "POST":
        reconciliation_date = _parse_date(request.form.get("reconciliation_date"))
        opening_cash = _parse_decimal(request.form.get("opening_cash"))
        if reconciliation_date is None:
            flash("Reconciliation date is required.", "warning")
        elif opening_cash is not None and opening_cash < 0:
            flash("Opening cash cannot be negative.", "warning")
        elif KaewaDailyReconciliation.query.filter_by(reconciliation_date=reconciliation_date).first():
            flash("A reconciliation already exists for this date.", "warning")
        else:
            reconciliation.reconciliation_date = reconciliation_date
            reconciliation.office_location = _clean(request.form.get("office_location")) or "Kaewa"
            reconciliation.opening_cash = opening_cash
            reconciliation.counted_cash = _parse_decimal(request.form.get("counted_cash"))
            if reconciliation.counted_cash is not None and reconciliation.counted_cash < 0:
                flash("Counted cash cannot be negative.", "warning")
                return render_template(
                    "admin/kaewa/reconciliation_form.html",
                    reconciliation=reconciliation,
                    statuses=KAEWA_RECONCILIATION_STATUSES,
                    action="Create",
                )
            reconciliation.stock_variance_notes = _clean(request.form.get("stock_variance_notes"))
            reconciliation.general_notes = _clean(request.form.get("general_notes"))
            _apply_reconciliation_sales_totals(reconciliation)
            _snapshot_reconciliation_lines(reconciliation)
            db.session.add(reconciliation)
            if _commit_or_rollback("Daily reconciliation"):
                return redirect(url_for("kaewa.reconciliations_detail", reconciliation_id=reconciliation.id))
    return render_template(
        "admin/kaewa/reconciliation_form.html",
        reconciliation=reconciliation,
        statuses=KAEWA_RECONCILIATION_STATUSES,
        action="Create",
    )


@kaewa_bp.route("/reconciliations/<int:reconciliation_id>", methods=["GET"])
@admin_required
def reconciliations_detail(reconciliation_id: int):
    reconciliation = KaewaDailyReconciliation.query.get_or_404(reconciliation_id)
    return render_template(
        "admin/kaewa/reconciliation_detail.html",
        reconciliation=reconciliation,
        lines=reconciliation.lines,
    )


@kaewa_bp.route("/reconciliations/<int:reconciliation_id>/edit", methods=["GET", "POST"])
@admin_required
def reconciliations_edit(reconciliation_id: int):
    reconciliation = KaewaDailyReconciliation.query.get_or_404(reconciliation_id)
    if reconciliation.status != "draft":
        flash("Submitted or reviewed reconciliations are locked.", "warning")
        return redirect(url_for("kaewa.reconciliations_detail", reconciliation_id=reconciliation.id))
    if request.method == "POST":
        counted_cash = _parse_decimal(request.form.get("counted_cash"))
        if counted_cash is not None and counted_cash < 0:
            flash("Counted cash cannot be negative.", "warning")
        else:
            reconciliation.counted_cash = counted_cash
            reconciliation.stock_variance_notes = _clean(request.form.get("stock_variance_notes"))
            reconciliation.general_notes = _clean(request.form.get("general_notes"))
            for line in reconciliation.lines:
                counted = _parse_decimal(request.form.get(f"counted_stock_qty_{line.id}"))
                if counted is not None and counted < 0:
                    flash("Counted stock cannot be negative.", "warning")
                    return render_template(
                        "admin/kaewa/reconciliation_form.html",
                        reconciliation=reconciliation,
                        statuses=KAEWA_RECONCILIATION_STATUSES,
                        action="Update",
                    )
                line.counted_stock_qty = counted
                line.notes = _clean(request.form.get(f"line_notes_{line.id}"))
            _recalculate_reconciliation(reconciliation)
            if _commit_or_rollback("Daily reconciliation"):
                return redirect(url_for("kaewa.reconciliations_detail", reconciliation_id=reconciliation.id))
    return render_template(
        "admin/kaewa/reconciliation_form.html",
        reconciliation=reconciliation,
        statuses=KAEWA_RECONCILIATION_STATUSES,
        action="Update",
    )


@kaewa_bp.route("/reconciliations/<int:reconciliation_id>/submit", methods=["POST"])
@admin_required
def reconciliations_submit(reconciliation_id: int):
    reconciliation = KaewaDailyReconciliation.query.get_or_404(reconciliation_id)
    if reconciliation.status != "draft":
        flash("Only draft reconciliations can be submitted.", "warning")
    else:
        reconciliation.status = "submitted"
        _commit_or_rollback("Daily reconciliation")
    return redirect(url_for("kaewa.reconciliations_detail", reconciliation_id=reconciliation.id))


@kaewa_bp.route("/reconciliations/<int:reconciliation_id>/review", methods=["POST"])
@admin_required
def reconciliations_review(reconciliation_id: int):
    reconciliation = KaewaDailyReconciliation.query.get_or_404(reconciliation_id)
    if reconciliation.status != "submitted":
        flash("Only submitted reconciliations can be reviewed.", "warning")
    else:
        reconciliation.status = "reviewed"
        reconciliation.reviewed_by_user_id = _current_admin_id()
        reconciliation.reviewed_at = utcnow_naive()
        _commit_or_rollback("Daily reconciliation")
    return redirect(url_for("kaewa.reconciliations_detail", reconciliation_id=reconciliation.id))


@kaewa_bp.route("/rural-services", methods=["GET"])
@admin_required
def rural_services_index():
    products = RuralServiceProduct.query.order_by(
        RuralServiceProduct.active.desc(),
        RuralServiceProduct.name.asc(),
    ).all()
    return render_template(
        "admin/kaewa/rural_services_index.html",
        product_summaries=[_product_summary(product) for product in products],
    )


@kaewa_bp.route("/rural-services/sales", methods=["GET"])
@admin_required
def rural_service_sales_index():
    sales = RuralServiceSale.query.order_by(RuralServiceSale.created_at.desc()).limit(200).all()
    return render_template("admin/kaewa/rural_service_sales_index.html", sales=sales)


@kaewa_bp.route("/rural-services/sales/new", methods=["GET", "POST"])
@admin_required
def rural_service_sales_new():
    sale = RuralServiceSale(sale_number=_next_rural_sale_number(), sale_date=date.today(), created_by_user_id=_current_admin_id())
    products = RuralServiceProduct.query.filter_by(active=True).order_by(RuralServiceProduct.name.asc()).all()
    stakeholders = Stakeholder.query.order_by(Stakeholder.name.asc()).limit(300).all()
    if request.method == "POST":
        _populate_rural_service_sale(sale)
        item = _build_rural_service_sale_item(sale)
        if item is None:
            flash("Add at least one valid sale item.", "warning")
        else:
            sale.items.append(item)
            db.session.add(sale)
            if _commit_or_rollback("Rural services sale"):
                return redirect(url_for("kaewa.rural_service_sales_detail", sale_id=sale.id))
    return render_template(
        "admin/kaewa/rural_service_sale_form.html",
        sale=sale,
        products=products,
        stakeholders=stakeholders,
        payment_methods=RURAL_SALE_PAYMENT_METHODS,
        action="Create",
    )


@kaewa_bp.route("/rural-services/sales/<int:sale_id>", methods=["GET"])
@admin_required
def rural_service_sales_detail(sale_id: int):
    sale = RuralServiceSale.query.get_or_404(sale_id)
    return render_template(
        "admin/kaewa/rural_service_sale_detail.html",
        sale=sale,
        total=_sale_total(sale),
    )


@kaewa_bp.route("/rural-services/sales/<int:sale_id>/receipt", methods=["GET"])
@admin_required
def rural_service_sales_receipt(sale_id: int):
    sale = RuralServiceSale.query.get_or_404(sale_id)
    return render_template(
        "admin/kaewa/rural_service_sale_receipt.html",
        sale=sale,
        total=_sale_total(sale),
        generated_at=utcnow_naive(),
    )


@kaewa_bp.route("/rural-services/sales/<int:sale_id>/complete", methods=["POST"])
@admin_required
def rural_service_sales_complete(sale_id: int):
    sale = RuralServiceSale.query.get_or_404(sale_id)
    if sale.status != "draft":
        flash("Only draft sales can be completed.", "warning")
        return redirect(url_for("kaewa.rural_service_sales_detail", sale_id=sale.id))
    if not sale.items:
        flash("Sale must have at least one item before completion.", "warning")
        return redirect(url_for("kaewa.rural_service_sales_detail", sale_id=sale.id))

    for item in sale.items:
        if not item.product.active:
            flash("Inactive products cannot be sold.", "warning")
            return redirect(url_for("kaewa.rural_service_sales_detail", sale_id=sale.id))
        if item.quantity <= 0 or item.unit_price < 0:
            flash("Sale items must have positive quantity and non-negative price.", "warning")
            return redirect(url_for("kaewa.rural_service_sales_detail", sale_id=sale.id))
        if _product_stock_balance(item.product) < item.quantity:
            flash("Insufficient stock to complete this sale.", "warning")
            return redirect(url_for("kaewa.rural_service_sales_detail", sale_id=sale.id))

    for item in sale.items:
        db.session.add(
            RuralServiceStockMovement(
                product_id=item.product_id,
                movement_type="sale",
                quantity=item.quantity,
                unit_cost=item.unit_price,
                reference=sale.sale_number,
                notes=f"Rural services sale {sale.sale_number}",
                created_by_user_id=_current_admin_id(),
            )
        )
    sale.status = "completed"
    _commit_or_rollback("Rural services sale")
    return redirect(url_for("kaewa.rural_service_sales_detail", sale_id=sale.id))


@kaewa_bp.route("/rural-services/sales/<int:sale_id>/cancel", methods=["POST"])
@admin_required
def rural_service_sales_cancel(sale_id: int):
    sale = RuralServiceSale.query.get_or_404(sale_id)
    if sale.status == "cancelled":
        flash("Sale is already cancelled.", "warning")
        return redirect(url_for("kaewa.rural_service_sales_detail", sale_id=sale.id))
    if sale.status == "completed":
        for item in sale.items:
            db.session.add(
                RuralServiceStockMovement(
                    product_id=item.product_id,
                    movement_type="sale_reversal",
                    quantity=item.quantity,
                    unit_cost=item.unit_price,
                    reference=sale.sale_number,
                    notes=f"Cancelled rural services sale {sale.sale_number}",
                    created_by_user_id=_current_admin_id(),
                )
            )
    sale.status = "cancelled"
    _commit_or_rollback("Rural services sale")
    return redirect(url_for("kaewa.rural_service_sales_detail", sale_id=sale.id))


@kaewa_bp.route("/rural-services/products/new", methods=["GET", "POST"])
@admin_required
def rural_service_products_new():
    product = RuralServiceProduct(active=True)
    if request.method == "POST":
        _populate_rural_service_product(product)
        db.session.add(product)
        if _commit_or_rollback("Rural service product"):
            return redirect(url_for("kaewa.rural_service_products_detail", product_id=product.id))
    return render_template(
        "admin/kaewa/rural_service_product_form.html",
        product=product,
        categories=RURAL_PRODUCT_CATEGORIES,
        units=RURAL_PRODUCT_UNITS,
        action="Create",
    )


@kaewa_bp.route("/rural-services/products/<int:product_id>", methods=["GET"])
@admin_required
def rural_service_products_detail(product_id: int):
    product = RuralServiceProduct.query.get_or_404(product_id)
    return render_template(
        "admin/kaewa/rural_service_product_detail.html",
        product=product,
        stock=_product_stock_balance(product),
        low_stock=_product_summary(product)["low_stock"],
        movements=product.stock_movements,
    )


@kaewa_bp.route("/rural-services/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def rural_service_products_edit(product_id: int):
    product = RuralServiceProduct.query.get_or_404(product_id)
    if request.method == "POST":
        _populate_rural_service_product(product)
        if _commit_or_rollback("Rural service product"):
            return redirect(url_for("kaewa.rural_service_products_detail", product_id=product.id))
    return render_template(
        "admin/kaewa/rural_service_product_form.html",
        product=product,
        categories=RURAL_PRODUCT_CATEGORIES,
        units=RURAL_PRODUCT_UNITS,
        action="Update",
    )


@kaewa_bp.route("/rural-services/products/<int:product_id>/stock-movements/new", methods=["GET", "POST"])
@admin_required
def rural_service_stock_movements_new(product_id: int):
    product = RuralServiceProduct.query.get_or_404(product_id)
    movement = RuralServiceStockMovement(product_id=product.id)
    if request.method == "POST":
        movement_type = request.form.get("movement_type")
        quantity = _parse_decimal(request.form.get("quantity"))
        if movement_type not in RURAL_STOCK_MOVEMENT_TYPES:
            flash("Choose a valid stock movement type.", "warning")
        elif quantity is None or quantity <= 0:
            flash("Stock movement quantity must be greater than zero.", "warning")
        elif not product.active and movement_type != "adjustment_out":
            flash("Inactive products can only receive adjustment-out movements.", "warning")
        else:
            _populate_rural_service_stock_movement(movement, movement_type, quantity)
            db.session.add(movement)
            if _commit_or_rollback("Stock movement"):
                return redirect(url_for("kaewa.rural_service_products_detail", product_id=product.id))
    return render_template(
        "admin/kaewa/rural_service_stock_movement_form.html",
        product=product,
        movement=movement,
        movement_types=RURAL_STOCK_MOVEMENT_TYPES,
        action="Add",
    )


def _populate_rural_service_product(product: RuralServiceProduct) -> None:
    product.name = _clean(request.form.get("name")) or "Unnamed product"
    product.category = (
        request.form.get("category") if request.form.get("category") in RURAL_PRODUCT_CATEGORIES else "other"
    )
    product.unit = request.form.get("unit") if request.form.get("unit") in RURAL_PRODUCT_UNITS else "piece"
    product.sku = _clean(request.form.get("sku"))
    product.description = _clean(request.form.get("description"))
    product.reorder_level = _parse_decimal(request.form.get("reorder_level"))
    product.active = request.form.get("active") == "1"


def _populate_rural_service_sale(sale: RuralServiceSale) -> None:
    stakeholder_id = _parse_int(request.form.get("stakeholder_id"), 0)
    sale.stakeholder_id = stakeholder_id or None
    sale.buyer_name = _clean(request.form.get("buyer_name"))
    sale.buyer_phone = _clean(request.form.get("buyer_phone"))
    sale.sale_date = _parse_date(request.form.get("sale_date")) or date.today()
    sale.payment_method = (
        request.form.get("payment_method") if request.form.get("payment_method") in RURAL_SALE_PAYMENT_METHODS else "cash"
    )
    sale.payment_reference = _clean(request.form.get("payment_reference"))
    sale.notes = _clean(request.form.get("notes"))
    sale.created_by_user_id = sale.created_by_user_id or _current_admin_id()


def _build_rural_service_sale_item(sale: RuralServiceSale) -> RuralServiceSaleItem | None:
    product_id = _parse_int(request.form.get("product_id"), 0)
    product = db.session.get(RuralServiceProduct, product_id) if product_id else None
    quantity = _parse_decimal(request.form.get("quantity"))
    unit_price = _parse_decimal(request.form.get("unit_price"))
    if not product or not product.active:
        return None
    if quantity is None or quantity <= 0:
        return None
    if unit_price is None or unit_price < 0:
        return None
    return RuralServiceSaleItem(
        sale=sale,
        product_id=product.id,
        quantity=quantity,
        unit_price=unit_price,
        line_total=quantity * unit_price,
        notes=_clean(request.form.get("item_notes")),
    )


def _populate_rural_service_stock_movement(
    movement: RuralServiceStockMovement,
    movement_type: str,
    quantity: Decimal,
) -> None:
    movement.movement_type = movement_type
    movement.quantity = quantity
    movement.unit_cost = _parse_decimal(request.form.get("unit_cost"))
    movement.supplier_name = _clean(request.form.get("supplier_name"))
    movement.reference = _clean(request.form.get("reference"))
    movement.notes = _clean(request.form.get("notes"))
    movement.created_by_user_id = _current_admin_id()


@kaewa_bp.route("/holding-pens", methods=["GET"])
@admin_required
def holding_pens_index():
    pens = HoldingPen.query.order_by(HoldingPen.status.asc(), HoldingPen.name.asc()).all()
    return render_template(
        "admin/kaewa/holding_pens_index.html",
        pen_summaries=[_holding_pen_summary(pen) for pen in pens],
    )


@kaewa_bp.route("/holding-pens/new", methods=["GET", "POST"])
@admin_required
def holding_pens_new():
    pen = HoldingPen(office_location="Kaewa", status="active", animal_type="mixed")
    if request.method == "POST":
        _populate_holding_pen(pen)
        db.session.add(pen)
        if _commit_or_rollback("Holding pen"):
            return redirect(url_for("kaewa.holding_pens_detail", pen_id=pen.id))
    return render_template(
        "admin/kaewa/holding_pen_form.html",
        pen=pen,
        animal_types=HOLDING_PEN_ANIMAL_TYPES,
        statuses=HOLDING_PEN_STATUSES,
        action="Create",
    )


@kaewa_bp.route("/holding-pens/<int:pen_id>", methods=["GET"])
@admin_required
def holding_pens_detail(pen_id: int):
    pen = HoldingPen.query.get_or_404(pen_id)
    active_assignments = HoldingPenAssignment.query.filter_by(holding_pen_id=pen.id, status="active").order_by(
        HoldingPenAssignment.assigned_at.desc()
    ).all()
    released_assignments = HoldingPenAssignment.query.filter_by(holding_pen_id=pen.id, status="released").order_by(
        HoldingPenAssignment.released_at.desc(),
        HoldingPenAssignment.assigned_at.desc(),
    ).limit(25).all()
    eligible_intakes = FieldLivestockIntake.query.filter(FieldLivestockIntake.intake_status == "accepted").order_by(
        FieldLivestockIntake.created_at.desc()
    ).limit(100).all()
    return render_template(
        "admin/kaewa/holding_pen_detail.html",
        pen=pen,
        occupancy=_holding_pen_occupancy(pen),
        utilization=_holding_pen_summary(pen)["utilization"],
        remaining_capacity=_holding_pen_capacity_remaining(pen),
        active_assignments=active_assignments,
        released_assignments=released_assignments,
        activities=pen.activities,
        eligible_intakes=eligible_intakes,
        animal_types=INTAKE_ANIMAL_TYPES,
        release_reasons=HOLDING_RELEASE_REASONS,
        activity_types=HOLDING_ACTIVITY_TYPES,
    )


@kaewa_bp.route("/holding-pens/<int:pen_id>/edit", methods=["GET", "POST"])
@admin_required
def holding_pens_edit(pen_id: int):
    pen = HoldingPen.query.get_or_404(pen_id)
    if request.method == "POST":
        _populate_holding_pen(pen)
        if _commit_or_rollback("Holding pen"):
            return redirect(url_for("kaewa.holding_pens_detail", pen_id=pen.id))
    return render_template(
        "admin/kaewa/holding_pen_form.html",
        pen=pen,
        animal_types=HOLDING_PEN_ANIMAL_TYPES,
        statuses=HOLDING_PEN_STATUSES,
        action="Update",
    )


@kaewa_bp.route("/holding-pens/<int:pen_id>/assign", methods=["POST"])
@admin_required
def holding_pens_assign(pen_id: int):
    pen = HoldingPen.query.get_or_404(pen_id)
    intake_id = _parse_int(request.form.get("field_livestock_intake_id"), 0)
    intake = db.session.get(FieldLivestockIntake, intake_id) if intake_id else None
    animal_type = request.form.get("animal_type")
    count = _parse_int(request.form.get("count"), 0)
    estimated_weight = _parse_decimal(request.form.get("estimated_total_weight_kg"))
    notes = _clean(request.form.get("notes"))

    if intake:
        animal_type = intake.animal_type
        count = count or intake.count
        estimated_weight = estimated_weight if estimated_weight is not None else intake.estimated_total_weight_kg
        if intake.intake_status != "accepted":
            flash("Only accepted intake records can be assigned to holding pens.", "warning")
            return redirect(url_for("kaewa.holding_pens_detail", pen_id=pen.id))

    if pen.status != "active":
        flash("Only active holding pens can receive assignments.", "warning")
        return redirect(url_for("kaewa.holding_pens_detail", pen_id=pen.id))
    if count <= 0:
        flash("Assignment count must be greater than zero.", "warning")
        return redirect(url_for("kaewa.holding_pens_detail", pen_id=pen.id))
    if animal_type not in INTAKE_ANIMAL_TYPES:
        flash("Choose a valid animal type for this assignment.", "warning")
        return redirect(url_for("kaewa.holding_pens_detail", pen_id=pen.id))
    if pen.animal_type != "mixed" and animal_type != pen.animal_type:
        flash("Animal type must match the holding pen unless the pen is mixed.", "warning")
        return redirect(url_for("kaewa.holding_pens_detail", pen_id=pen.id))

    remaining = _holding_pen_capacity_remaining(pen)
    if remaining is not None and count > remaining:
        flash("Assignment exceeds holding pen capacity.", "warning")
        return redirect(url_for("kaewa.holding_pens_detail", pen_id=pen.id))

    assignment = HoldingPenAssignment(
        holding_pen_id=pen.id,
        field_livestock_intake_id=intake.id if intake else None,
        animal_type=animal_type,
        count=count,
        estimated_total_weight_kg=estimated_weight,
        notes=notes,
        created_by_user_id=_current_admin_id(),
    )
    db.session.add(assignment)
    db.session.flush()
    _record_holding_pen_activity(
        pen,
        "assignment",
        notes or f"Assigned {count} {animal_type} to holding pen.",
        assignment.id,
    )
    if _commit_or_rollback("Holding pen assignment"):
        return redirect(url_for("kaewa.holding_pens_detail", pen_id=pen.id))
    return redirect(url_for("kaewa.holding_pens_detail", pen_id=pen.id))


@kaewa_bp.route("/holding-assignments/<int:assignment_id>/release", methods=["POST"])
@admin_required
def holding_assignments_release(assignment_id: int):
    assignment = HoldingPenAssignment.query.get_or_404(assignment_id)
    reason = request.form.get("release_reason")
    notes = _clean(request.form.get("notes"))
    if assignment.status == "released":
        flash("Assignment is already released.", "info")
        return redirect(url_for("kaewa.holding_pens_detail", pen_id=assignment.holding_pen_id))
    assignment.status = "released"
    assignment.released_at = utcnow_naive()
    assignment.release_reason = reason if reason in HOLDING_RELEASE_REASONS else "other"
    _record_holding_pen_activity(
        assignment.holding_pen,
        "release",
        notes or f"Released {assignment.count} {assignment.animal_type}.",
        assignment.id,
    )
    _commit_or_rollback("Holding pen release")
    return redirect(url_for("kaewa.holding_pens_detail", pen_id=assignment.holding_pen_id))


@kaewa_bp.route("/holding-pens/<int:pen_id>/activities/new", methods=["POST"])
@admin_required
def holding_pen_activities_new(pen_id: int):
    pen = HoldingPen.query.get_or_404(pen_id)
    activity_type = request.form.get("activity_type")
    description = _clean(request.form.get("description"))
    assignment_id = _parse_int(request.form.get("holding_pen_assignment_id"), 0) or None
    _record_holding_pen_activity(
        pen,
        activity_type if activity_type in HOLDING_ACTIVITY_TYPES else "note",
        description,
        assignment_id,
    )
    _commit_or_rollback("Holding pen activity")
    return redirect(url_for("kaewa.holding_pens_detail", pen_id=pen.id))


def _populate_holding_pen(pen: HoldingPen) -> None:
    pen.name = _clean(request.form.get("name")) or "Unnamed holding pen"
    pen.office_location = _clean(request.form.get("office_location")) or "Kaewa"
    pen.animal_type = (
        request.form.get("animal_type") if request.form.get("animal_type") in HOLDING_PEN_ANIMAL_TYPES else "mixed"
    )
    capacity = _parse_int(request.form.get("capacity_count"), 0)
    pen.capacity_count = capacity or None
    pen.status = request.form.get("status") if request.form.get("status") in HOLDING_PEN_STATUSES else "active"
    pen.notes = _clean(request.form.get("notes"))


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
    aggregation_batches = AggregationBatch.query.filter_by(animal_type=intake.animal_type).order_by(
        AggregationBatch.date_received.desc(),
        AggregationBatch.id.desc(),
    ).limit(100).all()
    holding_pen_summaries = [
        _holding_pen_summary(pen)
        for pen in HoldingPen.query.filter(
            HoldingPen.status == "active",
            sa.or_(HoldingPen.animal_type == intake.animal_type, HoldingPen.animal_type == "mixed"),
        )
        .order_by(HoldingPen.name.asc())
        .all()
    ]
    return render_template(
        "admin/kaewa/intake_detail.html",
        intake=intake,
        statuses=INTAKE_STATUSES,
        handoff_statuses=HANDOFF_STATUSES,
        aggregation_batches=aggregation_batches,
        handoff_events=intake.activities,
        holding_pen_summaries=holding_pen_summaries,
    )


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


@kaewa_bp.route("/intakes/<int:intake_id>/handoff/ready", methods=["POST"])
@admin_required
def intakes_mark_ready_for_aggregation(intake_id: int):
    intake = FieldLivestockIntake.query.get_or_404(intake_id)
    notes = _clean(request.form.get("handoff_notes"))
    if intake.intake_status != "accepted":
        flash("Only accepted intake records can be marked ready for aggregation.", "warning")
        return redirect(url_for("kaewa.intakes_detail", intake_id=intake.id))

    previous_status = intake.handoff_status or "none"
    intake.handoff_status = "ready_for_aggregation"
    intake.handoff_notes = notes
    intake.reviewed_by_user_id = _current_admin_id()
    intake.reviewed_at = utcnow_naive()
    _record_intake_activity(
        intake,
        "handoff_ready_for_aggregation",
        previous_status,
        intake.handoff_status,
        notes,
    )
    _commit_or_rollback("Livestock intake handoff")
    return redirect(url_for("kaewa.intakes_detail", intake_id=intake.id))


@kaewa_bp.route("/intakes/<int:intake_id>/handoff/link-batch", methods=["POST"])
@admin_required
def intakes_link_aggregation_batch(intake_id: int):
    intake = FieldLivestockIntake.query.get_or_404(intake_id)
    aggregation_batch_id = _parse_int(request.form.get("aggregation_batch_id"), 0)
    batch = db.session.get(AggregationBatch, aggregation_batch_id) if aggregation_batch_id else None
    notes = _clean(request.form.get("handoff_notes"))

    if intake.intake_status != "accepted":
        flash("Only accepted intake records can be linked to aggregation batches.", "warning")
        return redirect(url_for("kaewa.intakes_detail", intake_id=intake.id))
    if intake.handoff_status != "ready_for_aggregation":
        flash("Mark the intake ready for aggregation before linking a batch.", "warning")
        return redirect(url_for("kaewa.intakes_detail", intake_id=intake.id))
    if not batch or batch.animal_type != intake.animal_type:
        flash("Choose an existing aggregation batch for the same animal type.", "warning")
        return redirect(url_for("kaewa.intakes_detail", intake_id=intake.id))

    previous_status = intake.handoff_status
    intake.linked_aggregation_batch_id = batch.id
    intake.handoff_status = "handed_off"
    intake.intake_status = "transferred_to_aggregation"
    intake.handoff_notes = notes or intake.handoff_notes
    intake.reviewed_by_user_id = intake.reviewed_by_user_id or _current_admin_id()
    intake.reviewed_at = intake.reviewed_at or utcnow_naive()
    _record_intake_activity(
        intake,
        "handoff_linked_aggregation_batch",
        previous_status,
        intake.handoff_status,
        notes or f"Linked to aggregation batch #{batch.id}.",
    )
    _commit_or_rollback("Livestock intake handoff")
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
