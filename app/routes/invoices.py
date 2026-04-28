# app/routes/invoices.py
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Iterable

from flask import Blueprint, flash, current_app, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import (
    Buyer,
    ContractDocument,
    InventoryLot,
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    InvoicePayment,
)

bp = Blueprint("invoices", __name__, url_prefix="/admin/invoices")


def money(value) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def qty(value) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def next_invoice_number() -> str:
    last = Invoice.query.order_by(Invoice.id.desc()).first()
    next_id = (last.id + 1) if last else 1
    return f"INV-{next_id:05d}"


def get_lot_label(lot: InventoryLot) -> str:
    batch_no = getattr(lot, "lot_number", None) or getattr(lot, "batch_number", None)
    product = getattr(lot, "product_type", None) or getattr(lot, "description", None)

    if batch_no and product:
        return f"{product} - {batch_no}"
    if product:
        return product
    if batch_no:
        return f"Inventory Lot {batch_no}"
    return f"Processed meat - Lot #{lot.id}"


def deduct_inventory_lot(lot: InventoryLot, requested_kg: Decimal) -> None:
    available = qty(lot.available_kg)

    if requested_kg <= 0:
        raise ValueError("Quantity must be greater than zero.")

    if requested_kg > available:
        raise ValueError(
            f"Insufficient inventory. Lot #{lot.id} has only {available}kg available."
        )

    lot.available_kg = available - requested_kg

    if lot.available_kg <= 0:
        lot.available_kg = Decimal("0.00")
        lot.status = "sold"


def add_invoice_items_from_inventory(
    invoice: Invoice,
    lot_ids: Iterable[str],
    quantities: Iterable[str],
    unit_prices: Iterable[str],
) -> Invoice:
    subtotal = Decimal("0.00")

    for lot_id, quantity_raw, price_raw in zip(lot_ids, quantities, unit_prices):
        if not lot_id or not quantity_raw or not price_raw:
            continue

        lot = InventoryLot.query.get(int(lot_id))
        if not lot:
            raise ValueError("Selected inventory lot was not found.")

        requested_kg = qty(quantity_raw)
        unit_price = money(price_raw)
        line_total = money(requested_kg * unit_price)

        deduct_inventory_lot(lot, requested_kg)

        invoice.items.append(
            InvoiceItem(
                inventory_lot_id=lot.id,
                description=get_lot_label(lot),
                quantity=requested_kg,
                unit="kg",
                unit_price=unit_price,
                line_total=line_total,
            )
        )

        subtotal += line_total

    if not invoice.items:
        raise ValueError("Add at least one inventory item.")

    invoice.subtotal = money(subtotal)
    invoice.tax = money(invoice.tax)
    invoice.total = money(invoice.subtotal + invoice.tax)
    invoice.deposit_paid = money(invoice.deposit_paid)
    invoice.balance = money(invoice.total - invoice.deposit_paid)

    if invoice.balance <= 0 and invoice.total > 0:
        invoice.status = InvoiceStatus.PAID
    elif invoice.deposit_paid > 0:
        invoice.status = InvoiceStatus.PARTIALLY_PAID
    else:
        invoice.status = InvoiceStatus.ISSUED

    return invoice


@bp.get("")
@login_required
def list_invoices():
    invoices = Invoice.query.order_by(Invoice.created_at.desc()).all()
    return render_template("invoices/list.html", invoices=invoices)


@bp.get("/new")
@login_required
def new_invoice():
    batch_id = request.args.get("batch_id", type=int)
    selected_contract_document_id = request.args.get("contract_document_id", type=int)

    buyers = Buyer.query.order_by(Buyer.name.asc()).all()

    contract_documents = (
        ContractDocument.query
        .order_by(ContractDocument.uploaded_at.desc())
        .all()
    )

    inventory_query = InventoryLot.query.filter(InventoryLot.available_kg > 0)

    if batch_id:
        inventory_query = inventory_query.filter(
            InventoryLot.processing_batch_id == batch_id
        )

    inventory_lots = (
        inventory_query
        .order_by(InventoryLot.created_at.desc())
        .all()
    )

    return render_template(
        "invoices/new.html",
        buyers=buyers,
        contract_documents=contract_documents,
        inventory_lots=inventory_lots,
        selected_batch_id=batch_id,
        selected_contract_document_id=selected_contract_document_id,
    )

@bp.post("/new")
@login_required
def create_invoice():
    try:
        buyer_id = request.form.get("buyer_id", type=int)
        contract_document_id = request.form.get("contract_document_id", type=int)

        currency = (request.form.get("currency") or "USD").strip().upper()
        deposit_paid = money(request.form.get("deposit_paid"))
        tax = money(request.form.get("tax"))
        notes = (request.form.get("notes") or "").strip()
        terms = (request.form.get("terms") or "").strip()

        if not buyer_id:
            raise ValueError("Buyer is required.")

        if not contract_document_id:
            raise ValueError("Contract document is required.")

        buyer = Buyer.query.get(buyer_id)
        if not buyer:
            raise ValueError("Selected buyer was not found.")

        contract_document = ContractDocument.query.get(contract_document_id)
        if not contract_document:
            raise ValueError("Selected contract document was not found.")

        invoice = Invoice(
            invoice_number=next_invoice_number(),
            buyer_id=buyer.id,
            contract_document_id=contract_document.id,
            contract_id=contract_document.contract_id,
            currency=currency or "USD",
            deposit_paid=deposit_paid,
            tax=tax,
            notes=notes,
            terms=terms,
            status=InvoiceStatus.ISSUED,
        )

        if hasattr(invoice, "issued_by_user_id") and current_user.is_authenticated:
            invoice.issued_by_user_id = current_user.id

        add_invoice_items_from_inventory(
            invoice=invoice,
            lot_ids=request.form.getlist("inventory_lot_id[]"),
            quantities=request.form.getlist("quantity[]"),
            unit_prices=request.form.getlist("unit_price[]"),
        )

        if invoice.deposit_paid and invoice.deposit_paid > 0:
            from app.services.invoice_payments import next_receipt_number

            initial_payment = InvoicePayment(
                receipt_number=next_receipt_number(),
                invoice=invoice,
                amount=invoice.deposit_paid,
                method="deposit",
                reference="Initial deposit",
                notes="Deposit recorded during invoice creation.",
            )
            db.session.add(initial_payment)

        db.session.add(invoice)
        db.session.commit()

        flash(f"Invoice {invoice.invoice_number} created successfully.", "success")
        return redirect(url_for("invoices.view_invoice", invoice_id=invoice.id))

    except ValueError as e:
        db.session.rollback()
        flash(str(e), "error")
        return redirect(url_for("invoices.new_invoice"))

    except Exception as e:
        db.session.rollback()
        print("Invoice creation error:", e)
        flash("Invoice could not be created. Please try again.", "error")
        return redirect(url_for("invoices.new_invoice"))

@bp.get("/<int:invoice_id>")
@login_required
def view_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    return render_template("invoices/invoice_view.html", invoice=invoice)


@bp.post("/<int:invoice_id>/void")
@login_required
def void_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)

    if invoice.status == InvoiceStatus.VOID:
        flash("Invoice is already void.", "info")
        return redirect(url_for("invoices.view_invoice", invoice_id=invoice.id))

    try:
        for item in invoice.items:
            if item.inventory_lot:
                item.inventory_lot.available_kg = (
                    qty(item.inventory_lot.available_kg) + qty(item.quantity)
                )

                if item.inventory_lot.available_kg > 0 and item.inventory_lot.status == "sold":
                    item.inventory_lot.status = "available"

        invoice.status = InvoiceStatus.VOID

        if hasattr(invoice, "voided_at"):
            from app.models import utcnow_naive
            invoice.voided_at = utcnow_naive()

        db.session.commit()

        flash(
            f"Invoice {invoice.invoice_number} has been voided and inventory restored.",
            "success",
        )
        return redirect(url_for("invoices.view_invoice", invoice_id=invoice.id))

    except Exception as e:
        db.session.rollback()
        print("Invoice void error:", e)
        flash("Invoice could not be voided. Please try again.", "error")
        return redirect(url_for("invoices.view_invoice", invoice_id=invoice.id))
    
@bp.get("/<int:invoice_id>/pdf")
@login_required
def invoice_pdf(invoice_id):
    from app.utils.invoice_pdf import render_invoice_pdf

    invoice = Invoice.query.get_or_404(invoice_id)

    pdf_bytes = render_invoice_pdf(invoice)
    filename = f"Rizara_Invoice_{invoice.invoice_number or invoice.id}.pdf"

    return current_app.response_class(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"'
        },
    )    

@bp.post("/<int:invoice_id>/pay")
@login_required
def record_payment(invoice_id):
    from app.services.invoice_payments import record_invoice_payment

    invoice = Invoice.query.get_or_404(invoice_id)

    try:
        payment = record_invoice_payment(
            invoice=invoice,
            amount=request.form.get("amount"),
            method=request.form.get("method"),
            reference=request.form.get("reference"),
            notes=request.form.get("notes"),
        )

        db.session.commit()

        flash(
            f"Payment of {invoice.currency or 'USD'} {payment.amount:,.2f} recorded successfully.",
            "success",
        )
        return redirect(url_for("invoices.view_invoice", invoice_id=invoice.id))

    except ValueError as e:
        db.session.rollback()
        flash(str(e), "error")
        return redirect(url_for("invoices.view_invoice", invoice_id=invoice.id))

    except Exception as e:
        db.session.rollback()
        print("Invoice payment error:", e)
        flash("Payment could not be recorded. Please try again.", "error")
        return redirect(url_for("invoices.view_invoice", invoice_id=invoice.id))

@bp.get("/<int:invoice_id>/payments/<int:payment_id>/receipt")
@login_required
def payment_receipt(invoice_id, payment_id):
    from app.utils.receipt_pdf import render_payment_receipt_pdf

    invoice = Invoice.query.get_or_404(invoice_id)
    payment = InvoicePayment.query.get_or_404(payment_id)

    if payment.invoice_id != invoice.id:
        abort(404)

    pdf = render_payment_receipt_pdf(invoice, payment)

    filename = f"Receipt_{invoice.invoice_number}_{payment.id}.pdf"

    return current_app.response_class(
        pdf,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"'
        },
    )        

@bp.get("/buyers/<int:buyer_id>/statement")
@login_required
def buyer_statement(buyer_id):
    from app.utils.customer_statement_pdf import render_customer_statement_pdf

    buyer = Buyer.query.get_or_404(buyer_id)

    invoices = (
        Invoice.query
        .filter(Invoice.buyer_id == buyer.id)
        .order_by(Invoice.issue_date.asc(), Invoice.id.asc())
        .all()
    )

    pdf = render_customer_statement_pdf(buyer, invoices)

    filename = f"Statement_{buyer.name.replace(' ', '_')}.pdf"

    return current_app.response_class(
        pdf,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )