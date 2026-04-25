from __future__ import annotations

import uuid
from datetime import date, datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.models import (
    AggregationBatch,
    Farmer,
    Goat,
    MarketPurchase,
    MarketPurchaseExpense,
    MarketPurchaseLine,
    Sheep,
    Cattle,
)
from app.utils.guards import admin_required
from app.utils.request_parsers import parse_date, parse_float, parse_int
from app.utils.time_helpers import utcnow_naive

market_purchase_bp = Blueprint("market_purchase", __name__)


def commit_or_rollback(action: str) -> bool:
    try:
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        current_app.logger.exception("%s failed", action)
        flash(f"{action} failed. Please try again.", "danger")
        return False


def get_animal_model(animal_type: str):
    model_map = {
        "goat": Goat,
        "sheep": Sheep,
        "cattle": Cattle,
    }
    model = model_map.get((animal_type or "").strip().lower())
    if model is None:
        raise ValueError(f"Unsupported animal type: {animal_type}")
    return model


def generate_animal_code(animal_type: str, farmer_id: int) -> str:
    year = datetime.utcnow().year
    Model = get_animal_model(animal_type)

    last_animal = (
        Model.query
        .filter(Model.farmer_id == farmer_id, Model.rizara_id.like("RZ-%"))
        .order_by(Model.created_at.desc())
        .first()
    )

    last_seq = 0
    if last_animal and getattr(last_animal, "rizara_id", None):
        try:
            last_seq = int(last_animal.rizara_id.split("-")[-1])
        except (ValueError, IndexError):
            last_seq = 0

    return f"RZ-{animal_type.upper()}-{year}-{farmer_id}-{last_seq + 1:03d}"


@market_purchase_bp.route("/market-purchases/new", methods=["GET", "POST"])
@admin_required
def market_purchase_new():
    batches = AggregationBatch.query.order_by(AggregationBatch.id.desc()).all()

    if request.method == "POST":
        aggregation_batch_id = parse_int(request.form.get("aggregation_batch_id"))
        create_new_batch = (request.form.get("create_new_batch") or "").strip() == "yes"

        animal_type = (request.form.get("animal_type") or "").strip().lower()
        market_name = (request.form.get("market_name") or "").strip()
        purchase_date = parse_date(request.form.get("purchase_date")) or date.today()
        vendor_name = (request.form.get("vendor_name") or "").strip() or None
        broker_name = (request.form.get("broker_name") or "").strip() or None
        reference = (request.form.get("reference") or "").strip() or None
        notes = (request.form.get("notes") or "").strip() or None

        if not animal_type or not market_name:
            flash("Animal type and market name are required.", "danger")
            return redirect(request.url)

        batch = None

        if aggregation_batch_id:
            batch = AggregationBatch.query.get(aggregation_batch_id)
            if not batch:
                flash("Selected aggregation batch was not found.", "danger")
                return redirect(request.url)

            if (batch.animal_type or "").strip().lower() != animal_type:
                flash(
                    "Selected aggregation batch animal type does not match the market purchase animal type.",
                    "danger",
                )
                return redirect(request.url)

        elif create_new_batch:
            site_name = (request.form.get("site_name") or "").strip()
            date_received = parse_date(request.form.get("date_received")) or date.today()

            if not site_name:
                flash("Site name is required when creating a new aggregation batch.", "danger")
                return redirect(request.url)

            batch = AggregationBatch(
                animal_type=animal_type,
                site_name=site_name,
                date_received=date_received,
                created_by_user_id=current_user.id,
            )
            db.session.add(batch)
            db.session.flush()

        else:
            flash("Select an existing aggregation batch or create a new one.", "danger")
            return redirect(request.url)

        purchase = MarketPurchase(
            aggregation_batch_id=batch.id,
            animal_type=animal_type,
            purchase_date=purchase_date,
            market_name=market_name,
            vendor_name=vendor_name,
            broker_name=broker_name,
            reference=reference,
            notes=notes,
            created_by_user_id=current_user.id,
        )
        db.session.add(purchase)

        if not commit_or_rollback("Create market purchase"):
            return redirect(request.url)

        flash("Market purchase created. Add purchase lines next.", "success")
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    return render_template(
        "aggregation/market_purchase_new.html",
        batches=batches,
        date=date,
        current_year=datetime.utcnow().year,
    )


@market_purchase_bp.route("/market-purchases")
@admin_required
def market_purchase_list():
    purchases = MarketPurchase.query.order_by(MarketPurchase.created_at.desc()).all()
    return render_template(
        "aggregation/market_purchase_list.html",
        purchases=purchases,
        current_year=datetime.utcnow().year,
    )


@market_purchase_bp.route("/market-purchases/<int:purchase_id>", methods=["GET", "POST"])
@admin_required
def market_purchase_detail(purchase_id):
    purchase = MarketPurchase.query.get_or_404(purchase_id)

    if request.method == "POST":
        qty = parse_int(request.form.get("qty"))
        unit_price = parse_float(request.form.get("unit_price_kes"))

        if not qty or unit_price is None:
            flash("Quantity and unit price are required.", "danger")
            return redirect(request.url)

        line = MarketPurchaseLine(
            market_purchase_id=purchase.id,
            qty=qty,
            unit_price_kes=unit_price,
            total_price_kes=qty * unit_price,
            estimated_live_weight_per_head_kg=parse_float(request.form.get("live_weight")),
            estimated_carcass_weight_per_head_kg=parse_float(request.form.get("carcass_weight")),
            avg_age_months=parse_int(request.form.get("avg_age_months")),
            weight_method=(request.form.get("weight_method") or "").strip() or None,
            notes=(request.form.get("notes") or "").strip() or None,
        )
        db.session.add(line)

        if not commit_or_rollback("Add purchase line"):
            return redirect(request.url)

        flash("Purchase line added.", "success")
        return redirect(request.url)

    return render_template(
        "aggregation/market_purchase_detail.html",
        purchase=purchase,
        current_year=datetime.utcnow().year,
    )


@market_purchase_bp.route("/market-purchases/<int:purchase_id>/lines/<int:line_id>/edit", methods=["POST"])
@admin_required
def market_purchase_edit_line(purchase_id, line_id):
    purchase = MarketPurchase.query.get_or_404(purchase_id)
    line = MarketPurchaseLine.query.get_or_404(line_id)

    if line.market_purchase_id != purchase.id:
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    qty = parse_int(request.form.get("qty"))
    unit_price = parse_float(request.form.get("unit_price_kes"))

    if not qty or unit_price is None:
        flash("Quantity and unit price are required.", "danger")
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    line.qty = qty
    line.unit_price_kes = unit_price
    line.total_price_kes = qty * unit_price
    line.estimated_live_weight_per_head_kg = parse_float(request.form.get("live_weight"))
    line.estimated_carcass_weight_per_head_kg = parse_float(request.form.get("carcass_weight"))
    line.avg_age_months = parse_int(request.form.get("avg_age_months"))
    line.weight_method = (request.form.get("weight_method") or "").strip() or None
    line.notes = (request.form.get("notes") or "").strip() or None

    if not commit_or_rollback("Update purchase line"):
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    flash("Purchase line updated.", "success")
    return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))


@market_purchase_bp.route("/market-purchases/<int:purchase_id>/lines/<int:line_id>/delete", methods=["POST"])
@admin_required
def market_purchase_delete_line(purchase_id, line_id):
    purchase = MarketPurchase.query.get_or_404(purchase_id)
    line = MarketPurchaseLine.query.get_or_404(line_id)

    if line.market_purchase_id != purchase.id:
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    db.session.delete(line)

    if not commit_or_rollback("Delete purchase line"):
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    flash("Purchase line deleted.", "success")
    return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))


@market_purchase_bp.route("/market-purchases/<int:purchase_id>/expenses", methods=["POST"])
@admin_required
def market_purchase_add_expense(purchase_id):
    purchase = MarketPurchase.query.get_or_404(purchase_id)

    expense_type = (request.form.get("expense_type") or "").strip()
    amount = parse_float(request.form.get("amount"))

    if not expense_type or amount is None:
        flash("Expense type and amount are required.", "danger")
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    expense = MarketPurchaseExpense(
        aggregation_batch_id=purchase.aggregation_batch_id,
        market_purchase_id=purchase.id,
        expense_type=expense_type,
        amount=amount,
        incurred_date=parse_date(request.form.get("incurred_date")) or date.today(),
        paid_to=(request.form.get("paid_to") or "").strip() or None,
        reference=(request.form.get("reference") or "").strip() or None,
        notes=(request.form.get("notes") or "").strip() or None,
        created_by_user_id=current_user.id,
    )
    db.session.add(expense)

    if not commit_or_rollback("Add expense"):
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    flash("Expense added.", "success")
    return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))


@market_purchase_bp.route("/market-purchases/<int:purchase_id>/expenses/<int:expense_id>/edit", methods=["POST"])
@admin_required
def market_purchase_edit_expense(purchase_id, expense_id):
    purchase = MarketPurchase.query.get_or_404(purchase_id)
    expense = MarketPurchaseExpense.query.get_or_404(expense_id)

    if expense.market_purchase_id != purchase.id:
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    expense_type = (request.form.get("expense_type") or "").strip()
    amount = parse_float(request.form.get("amount"))

    if not expense_type or amount is None:
        flash("Expense type and amount are required.", "danger")
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    expense.expense_type = expense_type
    expense.amount = amount
    expense.incurred_date = parse_date(request.form.get("incurred_date")) or expense.incurred_date
    expense.paid_to = (request.form.get("paid_to") or "").strip() or None
    expense.reference = (request.form.get("reference") or "").strip() or None
    expense.notes = (request.form.get("notes") or "").strip() or None

    if not commit_or_rollback("Update expense"):
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    flash("Expense updated.", "success")
    return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))


@market_purchase_bp.route("/market-purchases/<int:purchase_id>/expenses/<int:expense_id>/delete", methods=["POST"])
@admin_required
def market_purchase_delete_expense(purchase_id, expense_id):
    purchase = MarketPurchase.query.get_or_404(purchase_id)
    expense = MarketPurchaseExpense.query.get_or_404(expense_id)

    if expense.market_purchase_id != purchase.id:
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    db.session.delete(expense)

    if not commit_or_rollback("Delete expense"):
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    flash("Expense deleted.", "success")
    return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))


@market_purchase_bp.route("/market-purchases/<int:purchase_id>/generate-animals", methods=["POST"])
@admin_required
def generate_animals_from_market_purchase(purchase_id):
    purchase = MarketPurchase.query.get_or_404(purchase_id)

    if (purchase.status or "").strip().lower() in {"processed", "converted", "finalized"}:
        flash("Animals have already been generated for this purchase.", "warning")
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    animal_type = (purchase.animal_type or "").strip().lower()
    if animal_type != "goat":
        flash("This temporary generator currently supports goats only.", "danger")
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    total_created = 0

    for line in purchase.lines:
        qty = int(line.qty or 0)
        for i in range(qty):
            goat = Goat(
                id=uuid.uuid4(),
                farmer_tag=f"MP-{purchase.id}-{total_created + 1:03d}",
                rizara_id=f"RZ-MP-{purchase.id}-{total_created + 1:03d}",
                sex=None,
                breed=None,
                status="aggregated",
                farmer_id=1,  # temporary placeholder
                is_active=True,
                aggregation_batch_id=purchase.aggregation_batch_id,
                aggregated_at=utcnow_naive(),
                aggregated_by_user_id=current_user.id,
                live_weight_kg=line.estimated_live_weight_per_head_kg,
                weight_method=(line.weight_method or "estimated").strip() or "estimated",
                purchase_price_per_head=line.unit_price_kes,
                purchase_currency="KES",
            )
            db.session.add(goat)
            total_created += 1

    purchase.status = "converted"

    if not commit_or_rollback("Generate animals from market purchase"):
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    flash(f"{total_created} animals generated and aggregated successfully.", "success")
    return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))


@market_purchase_bp.route("/market-purchases/<int:purchase_id>/finalize", methods=["POST"])
@admin_required
def market_purchase_finalize(purchase_id):
    purchase = MarketPurchase.query.get_or_404(purchase_id)

    if (purchase.status or "").strip().lower() in {"finalized", "converted"}:
        flash("This market purchase has already been finalized.", "warning")
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    if not purchase.aggregation_batch_id:
        flash("This market purchase is not linked to an aggregation batch.", "danger")
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    if not purchase.lines:
        flash("Add at least one purchase line before finalizing.", "danger")
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    animal_type = (purchase.animal_type or "").strip().lower()
    Model = get_animal_model(animal_type)

    batch = AggregationBatch.query.get_or_404(purchase.aggregation_batch_id)
    if (batch.animal_type or "").strip().lower() != animal_type:
        flash("Aggregation batch type does not match purchase animal type.", "danger")
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    source_farmer = Farmer.query.order_by(Farmer.id.asc()).first()
    if not source_farmer:
        flash("Create at least one farmer record before finalizing market purchases.", "danger")
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    created = 0

    for line in purchase.lines:
        qty = int(line.qty or 0)
        if qty <= 0:
            continue

        for _ in range(qty):
            serial = created + 1
            animal = Model(
                id=uuid.uuid4(),
                farmer_tag=f"MARKET-{purchase.id}-{serial:03d}",
                rizara_id=generate_animal_code(animal_type, source_farmer.id),
                sex=None,
                breed=None,
                estimated_dob=None,
                farmer_id=source_farmer.id,
                status="aggregated",
                is_active=True,
                aggregation_batch_id=batch.id,
                aggregated_at=utcnow_naive(),
                aggregated_by_user_id=current_user.id,
                live_weight_kg=line.estimated_live_weight_per_head_kg,
                weight_method=(line.weight_method or "estimated").strip() or "estimated",
                purchase_price_per_head=line.unit_price_kes,
                purchase_currency="KES",
            )
            db.session.add(animal)
            created += 1

    if created == 0:
        db.session.rollback()
        flash("No animals were generated from this market purchase.", "danger")
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    purchase.status = "received"

    if not commit_or_rollback("Finalize market purchase"):
        return redirect(url_for("market_purchase.market_purchase_detail", purchase_id=purchase.id))

    flash(f"Market purchase finalized successfully ({created} animals created).", "success")
    return redirect(url_for("main.dashboard"))