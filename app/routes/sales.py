from __future__ import annotations

from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Sale, SalePayment
from app.services.sale_service import calculate_sale_totals
from app.utils.time import utcnow_naive

bp = Blueprint("sales", __name__, url_prefix="/sales")


@bp.get("/<int:sale_id>")
@login_required
def view_sale(sale_id: int):
    sale = Sale.query.get_or_404(sale_id)
    return render_template("sales/view.html", sale=sale)


@bp.post("/<int:sale_id>/payments")
@login_required
def add_payment(sale_id: int):
    sale = Sale.query.get_or_404(sale_id)

    if sale.status == "cancelled":
        flash("Cannot add payment to a cancelled sale.", "danger")
        return redirect(url_for("sales.view_sale", sale_id=sale.id))

    payment_date = request.form.get("payment_date")
    payment_type = (request.form.get("payment_type") or "").strip()
    payment_method = (request.form.get("payment_method") or "").strip() or None
    reference_number = (request.form.get("reference_number") or "").strip() or None
    notes = (request.form.get("notes") or "").strip() or None
    raw_amount = (request.form.get("amount") or "").strip()

    if not payment_date:
        flash("Payment date is required.", "danger")
        return redirect(url_for("sales.view_sale", sale_id=sale.id))

    if not payment_type:
        flash("Payment type is required.", "danger")
        return redirect(url_for("sales.view_sale", sale_id=sale.id))

    try:
        amount = Decimal(raw_amount)
    except (InvalidOperation, TypeError):
        flash("Enter a valid payment amount.", "danger")
        return redirect(url_for("sales.view_sale", sale_id=sale.id))

    if amount <= 0:
        flash("Payment amount must be greater than zero.", "danger")
        return redirect(url_for("sales.view_sale", sale_id=sale.id))

    payment = SalePayment(
        sale_id=sale.id,
        payment_date=payment_date,
        payment_type=payment_type,
        payment_method=payment_method,
        amount=amount,
        reference_number=reference_number,
        notes=notes,
        created_by_user_id=getattr(current_user, "id", None),
        created_at=utcnow_naive(),
    )

    db.session.add(payment)

    # Recalculate totals after adding the new payment
    db.session.flush()
    calculate_sale_totals(sale)

    db.session.commit()

    flash("Payment recorded successfully.", "success")
    return redirect(url_for("sales.view_sale", sale_id=sale.id))


@bp.post("/<int:sale_id>/confirm")
@login_required
def confirm_sale(sale_id: int):
    sale = Sale.query.get_or_404(sale_id)

    if sale.status == "cancelled":
        flash("Cancelled sales cannot be confirmed.", "danger")
        return redirect(url_for("sales.view_sale", sale_id=sale.id))

    if not sale.items:
        flash("Cannot confirm a sale with no items.", "danger")
        return redirect(url_for("sales.view_sale", sale_id=sale.id))

    calculate_sale_totals(sale)

    sale.status = "confirmed"
    sale.updated_at = utcnow_naive()

    db.session.commit()

    flash("Sale confirmed successfully.", "success")
    return redirect(url_for("sales.view_sale", sale_id=sale.id))


@bp.post("/<int:sale_id>/complete")
@login_required
def complete_sale(sale_id: int):
    sale = Sale.query.get_or_404(sale_id)

    if sale.status == "cancelled":
        flash("Cancelled sales cannot be completed.", "danger")
        return redirect(url_for("sales.view_sale", sale_id=sale.id))

    if sale.status not in {"draft", "confirmed"}:
        flash("Only draft or confirmed sales can be completed.", "danger")
        return redirect(url_for("sales.view_sale", sale_id=sale.id))

    calculate_sale_totals(sale)

    sale.status = "completed"
    sale.updated_at = utcnow_naive()

    # Optional: push linked contract forward as fulfillment progresses
    if sale.contract:
        active_statuses = {"signed", "active", "partially_fulfilled"}
        if sale.contract.status in active_statuses:
            sale.contract.status = "partially_fulfilled"

    db.session.commit()

    flash("Sale marked as completed.", "success")
    return redirect(url_for("sales.view_sale", sale_id=sale.id))


@bp.post("/<int:sale_id>/cancel")
@login_required
def cancel_sale(sale_id: int):
    sale = Sale.query.get_or_404(sale_id)

    if sale.payments:
        flash("Cannot cancel a sale that already has recorded payments.", "danger")
        return redirect(url_for("sales.view_sale", sale_id=sale.id))

    sale.status = "cancelled"
    sale.updated_at = utcnow_naive()

    db.session.commit()

    flash("Sale cancelled.", "warning")
    return redirect(url_for("sales.view_sale", sale_id=sale.id))

@bp.post("/<int:sale_id>/authorize-processing")
@login_required
def authorize_processing(sale_id: int):
    sale = Sale.query.get_or_404(sale_id)

    if sale.status == "cancelled":
        flash("Cancelled sales cannot be authorized for processing.", "danger")
        return redirect(url_for("sales.view_sale", sale_id=sale.id))

    if sale.processing_authorized:
        flash("Processing is already authorized for this sale.", "info")
        return redirect(url_for("sales.view_sale", sale_id=sale.id))

    contract = sale.contract
    if not contract:
        flash("Sale is not linked to a contract.", "danger")
        return redirect(url_for("sales.view_sale", sale_id=sale.id))

    prepayment_ok = False
    lc_ok = False

    # Prepayment path
    if contract.prepayment_required:
        required_amount = Decimal("0")

        if contract.required_prepayment_amount:
            required_amount = Decimal(contract.required_prepayment_amount)
        elif contract.required_prepayment_percent and Decimal(sale.total_amount or 0) > 0:
            required_amount = (
                Decimal(sale.total_amount) * Decimal(contract.required_prepayment_percent) / Decimal("100")
            )

        if required_amount > 0 and Decimal(sale.amount_paid or 0) >= required_amount:
            prepayment_ok = True

    # LC path
    if contract.lc_required and contract.lc_status:
        if str(contract.lc_status).strip().lower() in {"confirmed", "approved", "available"}:
            lc_ok = True

    if not (prepayment_ok or lc_ok):
        flash("Processing can only be authorized after required prepayment is received or LC is confirmed.", "danger")
        return redirect(url_for("sales.view_sale", sale_id=sale.id))

    sale.processing_authorized = True
    sale.authorized_at = utcnow_naive()
    sale.updated_at = utcnow_naive()

    db.session.commit()

    flash("Processing authorized successfully.", "success")
    return redirect(url_for("sales.view_sale", sale_id=sale.id))