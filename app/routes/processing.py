from __future__ import annotations

from datetime import date, datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.models import (
    AggregationBatch,
    Buyer,
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    ProcessingBatch,
    ProcessingBatchSale,
    ProcessingYield,
)
from app.utils.guards import admin_required
from app.utils.request_parsers import parse_date, parse_float, parse_int, safe_enum_value
from app.utils.time_helpers import utcnow_naive
from app.utils.animal_helpers import (
    animal_label,
    get_animal_model,
    get_processing_relation_name,
)

processing_bp = Blueprint("processing", __name__)


def commit_or_rollback(action: str) -> bool:
    try:
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        current_app.logger.exception("%s failed", action)
        flash(f"{action} failed. Please try again.", "danger")
        return False


def get_processing_batch_or_404(batch_id: int) -> ProcessingBatch:
    return ProcessingBatch.query.get_or_404(batch_id)


def animals_in_processing_batch(batch: ProcessingBatch):
    animal_type = (batch.animal_type or "").strip().lower()
    if animal_type == "goat":
        return batch.goats
    if animal_type == "sheep":
        return batch.sheep
    if animal_type == "cattle":
        return batch.cattle
    return []


def generate_invoice_number() -> str:
    year = datetime.utcnow().year
    count = (db.session.query(db.func.count(Invoice.id)).scalar() or 0) + 1
    return f"RZ-INV-{year}-{count:04d}"


def register_processing_routes(animal_type: str, template_add: str):
    Model = get_animal_model(animal_type)
    relation_name = get_processing_relation_name(animal_type)
    label = animal_label(animal_type)
    endpoint_name = f"add_{animal_type}_processing"

    @processing_bp.route(
        f"/{animal_type}/processing/add",
        methods=["GET", "POST"],
        endpoint=endpoint_name,
    )
    @admin_required
    def add_processing():
        available_batches = (
            db.session.query(AggregationBatch)
            .join(Model, Model.aggregation_batch_id == AggregationBatch.id)
            .filter(
                AggregationBatch.animal_type == animal_type,
                AggregationBatch.is_locked.is_(False),
                Model.status == "aggregated",
                Model.is_active.is_(True),
            )
            .distinct()
            .order_by(AggregationBatch.created_at.desc())
            .all()
        )

        if request.method == "GET":
            return render_template(
                template_add,
                batches=available_batches,
                animal_type=animal_type,
                animal_label=label,
                date=date,
                current_year=datetime.utcnow().year,
            )

        facility = (request.form.get("facility") or "").strip()
        slaughter_date = parse_date(request.form.get("slaughter_date"))
        halal_cert_ref = (request.form.get("halal_cert_ref") or "").strip() or None
        aggregation_batch_id = parse_int(request.form.get("aggregation_batch_id"))

        if not facility:
            flash("Facility is required.", "danger")
            return redirect(request.url)

        if not aggregation_batch_id:
            flash("Select an aggregation batch.", "danger")
            return redirect(request.url)

        source_batch = db.session.get(AggregationBatch, aggregation_batch_id)
        if source_batch is None:
            flash("Selected aggregation batch was not found.", "danger")
            return redirect(request.url)

        if (source_batch.animal_type or "").strip().lower() != animal_type:
            flash("Selected aggregation batch does not match the processing animal type.", "danger")
            return redirect(request.url)

        if source_batch.is_locked:
            flash("Selected aggregation batch is locked and cannot be processed.", "danger")
            return redirect(request.url)

        animals = (
            Model.query
            .filter(
                Model.aggregation_batch_id == source_batch.id,
                Model.status == "aggregated",
                Model.is_active.is_(True),
            )
            .order_by(Model.created_at.asc())
            .all()
        )

        if not animals:
            flash(
                f"No eligible {label.lower()} were found in the selected aggregation batch.",
                "danger",
            )
            return redirect(request.url)

        processing_batch = ProcessingBatch(
            animal_type=animal_type,
            facility=facility,
            slaughter_date=slaughter_date,
            halal_cert_ref=halal_cert_ref,
            created_by_user_id=current_user.id,
        )
        db.session.add(processing_batch)

        relation = getattr(processing_batch, relation_name)
        attached_count = 0

        for animal in animals:
            animal.status = "processing"
            relation.append(animal)
            attached_count += 1

        source_batch.is_locked = True
        source_batch.locked_at = utcnow_naive()

        if not commit_or_rollback(f"Create {label} processing batch"):
            return redirect(request.url)

        flash(
            f"{label} processing batch created successfully from aggregation batch "
            f"#{source_batch.id} ({attached_count} animals).",
            "success",
        )
        return redirect(url_for("processing.view_invoiceable_batch", batch_id=processing_batch.id))


register_processing_routes("goat", "processing/batch_add.html")
register_processing_routes("sheep", "processing/batch_add.html")
register_processing_routes("cattle", "processing/batch_add.html")


@processing_bp.route("/processing/<int:batch_id>/overview")
@admin_required
def view_invoiceable_batch(batch_id):
    batch = get_processing_batch_or_404(batch_id)
    yield_record = ProcessingYield.query.filter_by(processing_batch_id=batch.id).first()
    sale = ProcessingBatchSale.query.filter_by(processing_batch_id=batch.id).first()
    invoice = Invoice.query.filter_by(processing_batch_sale_id=sale.id).first() if sale else None

    return render_template(
        "processing/batch_overview.html",
        batch=batch,
        yield_record=yield_record,
        sale=sale,
        invoice=invoice,
        current_year=datetime.utcnow().year,
    )


@processing_bp.route("/processing/<int:batch_id>/yield", methods=["GET", "POST"])
@admin_required
def record_processing_yield(batch_id):
    batch = get_processing_batch_or_404(batch_id)

    existing = ProcessingYield.query.filter_by(processing_batch_id=batch.id).first()
    if existing and request.method == "GET":
        flash("Yield already recorded for this batch.", "info")
        return redirect(url_for("processing.view_invoiceable_batch", batch_id=batch.id))

    if request.method == "POST":
        total_carcass_weight_kg = parse_float(request.form.get("total_carcass_weight_kg"))
        parts_included = request.form.get("parts_included_in_batch_sale") == "yes"
        parts_sold_separately = request.form.get("parts_sold_separately") == "yes"
        parts_notes = (request.form.get("parts_notes") or "").strip() or None

        if total_carcass_weight_kg is None:
            flash("Total carcass weight is required.", "danger")
            return redirect(request.url)

        yield_record = ProcessingYield(
            processing_batch_id=batch.id,
            total_carcass_weight_kg=total_carcass_weight_kg,
            parts_included_in_batch_sale=parts_included,
            parts_sold_separately=parts_sold_separately,
            parts_notes=parts_notes,
            recorded_by_user_id=current_user.id,
        )

        for animal in animals_in_processing_batch(batch):
            if (animal.status or "").strip().lower() == "processing":
                animal.status = "processed"

        db.session.add(yield_record)

        if not commit_or_rollback("Record processing yield"):
            return redirect(request.url)

        flash("Processing yield recorded successfully.", "success")
        return redirect(url_for("processing.view_invoiceable_batch", batch_id=batch.id))

    return render_template(
        "processing/yield_add.html",
        batch=batch,
        current_year=datetime.utcnow().year,
    )


@processing_bp.route("/processing/<int:batch_id>/sale", methods=["GET", "POST"])
@admin_required
def record_processing_batch_sale(batch_id):
    batch = get_processing_batch_or_404(batch_id)

    yield_record = ProcessingYield.query.filter_by(processing_batch_id=batch.id).first()
    if not yield_record:
        flash("Record processing yield first before selling the batch.", "danger")
        return redirect(url_for("processing.record_processing_yield", batch_id=batch.id))

    existing_sale = ProcessingBatchSale.query.filter_by(processing_batch_id=batch.id).first()
    if existing_sale and request.method == "GET":
        flash("Sale already recorded for this batch.", "info")
        return redirect(url_for("processing.generate_invoice_from_sale", sale_id=existing_sale.id))

    buyers = Buyer.query.order_by(Buyer.name.asc()).all()

    if request.method == "POST":
        existing_sale = ProcessingBatchSale.query.filter_by(processing_batch_id=batch.id).first()
        if existing_sale:
            flash("Sale already recorded for this batch. You can view the invoice.", "info")
            return redirect(url_for("processing.generate_invoice_from_sale", sale_id=existing_sale.id))

        buyer_id = parse_int(request.form.get("buyer_id"))
        buyer_name = (request.form.get("buyer_name") or "").strip() or None
        buyer_phone = (request.form.get("buyer_phone") or "").strip() or None
        buyer_email = (request.form.get("buyer_email") or "").strip() or None
        total_sale_price = parse_float(request.form.get("total_sale_price"))
        sale_date = parse_date(request.form.get("sale_date"))
        notes = (request.form.get("notes") or "").strip() or None

        if total_sale_price is None:
            flash("Total sale price is required.", "danger")
            return redirect(request.url)

        if buyer_id:
            buyer = Buyer.query.get(buyer_id)
            if not buyer:
                flash("Selected buyer not found.", "danger")
                return redirect(request.url)
        else:
            if not buyer_name:
                flash("Provide buyer name or select an existing buyer.", "danger")
                return redirect(request.url)
            buyer = Buyer(name=buyer_name, phone=buyer_phone, email=buyer_email)
            db.session.add(buyer)
            db.session.flush()

        sale = ProcessingBatchSale(
            processing_batch_id=batch.id,
            buyer_id=buyer.id,
            total_sale_price=total_sale_price,
            sale_date=sale_date or date.today(),
            notes=notes,
            recorded_by_user_id=current_user.id,
        )

        for animal in animals_in_processing_batch(batch):
            animal_status = (animal.status or "").strip().lower()
            if animal_status in {"processed", "processing"}:
                animal.status = "sold"

        db.session.add(sale)

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            existing_sale = ProcessingBatchSale.query.filter_by(processing_batch_id=batch.id).first()
            flash("Sale already recorded for this batch. You can view the invoice.", "info")
            if existing_sale:
                return redirect(url_for("processing.generate_invoice_from_sale", sale_id=existing_sale.id))
            return redirect(url_for("processing.view_invoiceable_batch", batch_id=batch.id))

        flash("Batch sale recorded. You can now generate the invoice.", "success")
        return redirect(url_for("processing.generate_invoice_from_sale", sale_id=sale.id))

    return render_template(
        "sales/batch_sale_add.html",
        batch=batch,
        yield_record=yield_record,
        buyers=buyers,
        current_year=datetime.utcnow().year,
    )


@processing_bp.route("/sales/<int:sale_id>/invoice/generate", methods=["GET"])
@admin_required
def generate_invoice_from_sale(sale_id):
    sale = ProcessingBatchSale.query.get_or_404(sale_id)
    batch = ProcessingBatch.query.get_or_404(sale.processing_batch_id)
    yield_record = ProcessingYield.query.filter_by(processing_batch_id=batch.id).first()

    existing_invoice = Invoice.query.filter_by(processing_batch_sale_id=sale.id).first()
    if existing_invoice:
        flash("Invoice already exists for this sale.", "info")
        return redirect(url_for("processing.view_invoice", invoice_id=existing_invoice.id))

    for attempt in range(2):
        invoice_number = generate_invoice_number()

        invoice = Invoice(
            invoice_number=invoice_number,
            buyer_id=sale.buyer_id,
            processing_batch_sale_id=sale.id,
            issue_date=date.today(),
            status=InvoiceStatus.ISSUED,
            issued_at=datetime.utcnow(),
            subtotal=float(sale.total_sale_price),
            tax=0.0,
            total=float(sale.total_sale_price),
            notes=sale.notes,
            terms="Payment due as agreed.",
            issued_by_user_id=current_user.id,
        )

        carcass_info = ""
        if yield_record:
            carcass_info = f" | Carcass weight: {yield_record.total_carcass_weight_kg} kg"
            if yield_record.parts_notes:
                carcass_info += f" | Parts: {yield_record.parts_notes}"

        item = InvoiceItem(
            description=f"Processing Batch #{batch.id} ({batch.animal_type}) - 1 lot{carcass_info}",
            quantity=1.0,
            unit_price=float(sale.total_sale_price),
            line_total=float(sale.total_sale_price),
        )

        db.session.add(invoice)
        db.session.flush()
        item.invoice_id = invoice.id
        db.session.add(item)

        try:
            db.session.commit()
            flash("Invoice generated successfully.", "success")
            return redirect(url_for("processing.view_invoice", invoice_id=invoice.id))
        except Exception:
            db.session.rollback()
            if attempt == 0:
                continue
            flash("Invoice generation failed due to a numbering conflict. Try again.", "danger")
            return redirect(url_for("processing.view_invoiceable_batch", batch_id=batch.id))

    flash("Invoice generation failed.", "danger")
    return redirect(url_for("processing.view_invoiceable_batch", batch_id=batch.id))


@processing_bp.route("/invoices/<int:invoice_id>")
@admin_required
def view_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    buyer = Buyer.query.get_or_404(invoice.buyer_id)
    items = InvoiceItem.query.filter_by(invoice_id=invoice.id).all()

    sale = ProcessingBatchSale.query.get_or_404(invoice.processing_batch_sale_id)
    batch = ProcessingBatch.query.get_or_404(sale.processing_batch_id)
    yield_record = ProcessingYield.query.filter_by(processing_batch_id=batch.id).first()

    return render_template(
        "invoices/invoice_view.html",
        invoice=invoice,
        buyer=buyer,
        items=items,
        sale=sale,
        batch=batch,
        yield_record=yield_record,
        current_year=datetime.utcnow().year,
        invoice_status_value=safe_enum_value(invoice.status),
    )


@processing_bp.route("/invoices/<int:invoice_id>/pdf", methods=["GET"])
@admin_required
def invoice_pdf(invoice_id):
    from app.utils.invoice_pdf import render_invoice_pdf

    invoice = Invoice.query.get_or_404(invoice_id)
    pdf_bytes = render_invoice_pdf(invoice)
    filename = f"Rizara_Invoice_{invoice.invoice_number or invoice.id}.pdf"

    return current_app.response_class(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )