from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.models import (
    AggregationBatch,
    Buyer,
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    InventoryLot,
    ProcessingBatch,
    ProcessingBatchSale,
    ProcessingYield,
    PipelineCase,
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
        batch_rows = (
            db.session.query(
                AggregationBatch.id.label("id"),
                AggregationBatch.site_name.label("site_name"),
                AggregationBatch.date_received.label("date_received"),
                AggregationBatch.created_at.label("created_at"),
                db.func.count(Model.id).label("animal_count"),
                db.func.coalesce(db.func.sum(Model.live_weight_kg), 0).label("estimated_kg"),
            )
            .join(Model, Model.aggregation_batch_id == AggregationBatch.id)
            .filter(
                AggregationBatch.animal_type == animal_type,
                AggregationBatch.is_locked.is_(False),
                Model.status == "aggregated",
                Model.is_active.is_(True),
            )
            .group_by(
                AggregationBatch.id,
                AggregationBatch.site_name,
                AggregationBatch.date_received,
                AggregationBatch.created_at,
            )
            .order_by(AggregationBatch.created_at.desc())
            .all()
        )

        available_batches = [
            {
                "id": row.id,
                "site_name": row.site_name,
                "date_received": row.date_received,
                "animal_count": int(row.animal_count or 0),
                "estimated_kg": float(row.estimated_kg or 0),
            }
            for row in batch_rows
        ]
        

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

        aggregation_batch_ids = [
            parse_int(batch_id)
            for batch_id in request.form.getlist("aggregation_batch_ids")
        ]
        aggregation_batch_ids = [batch_id for batch_id in aggregation_batch_ids if batch_id]

        if not facility:
            flash("Facility is required.", "danger")
            return redirect(request.url)

        if not aggregation_batch_ids:
            flash("Select at least one aggregation batch.", "danger")
            return redirect(request.url)

        source_batches = (
            AggregationBatch.query
            .filter(
                AggregationBatch.id.in_(aggregation_batch_ids),
                AggregationBatch.animal_type == animal_type,
                AggregationBatch.is_locked.is_(False),
            )
            .order_by(AggregationBatch.created_at.asc())
            .all()
        )

        if len(source_batches) != len(set(aggregation_batch_ids)):
            flash(
                "One or more selected aggregation batches were not found, locked, "
                "or do not match the processing animal type.",
                "danger",
            )
            return redirect(request.url)

        selected_batch_ids = [batch.id for batch in source_batches]

        animals = (
            Model.query
            .filter(
                Model.aggregation_batch_id.in_(selected_batch_ids),
                Model.status == "aggregated",
                Model.is_active.is_(True),
            )
            .order_by(Model.aggregation_batch_id.asc(), Model.created_at.asc())
            .all()
        )

        if not animals:
            flash(
                f"No eligible {label.lower()} were found in the selected aggregation batches.",
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

        for source_batch in source_batches:
            source_batch.is_locked = True
            source_batch.locked_at = utcnow_naive()

        if not commit_or_rollback(f"Create {label} processing batch"):
            return redirect(request.url)

        batch_numbers = ", ".join(f"#{batch.id}" for batch in source_batches)

        flash(
            f"{label} processing batch created successfully from "
            f"{len(source_batches)} aggregation batches ({batch_numbers}) "
            f"with {attached_count} animals.",
            "success",
        )

        return redirect(
            url_for(
                "processing.view_invoiceable_batch",
                batch_id=processing_batch.id,
            )
        )


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

    existing = ProcessingYield.query.filter_by(
        processing_batch_id=batch.id
    ).first()

    if existing and request.method == "GET":
        flash("Yield already recorded for this batch.", "info")
        return redirect(url_for("processing.view_invoiceable_batch", batch_id=batch.id))

    if request.method == "POST":
        total_carcass_weight_kg = parse_float(
            request.form.get("total_carcass_weight_kg")
        )
        parts_included = request.form.get("parts_included_in_batch_sale") == "yes"
        parts_sold_separately = request.form.get("parts_sold_separately") == "yes"
        parts_notes = (request.form.get("parts_notes") or "").strip() or None

        if total_carcass_weight_kg is None or total_carcass_weight_kg <= 0:
            flash("Total carcass weight must be greater than zero.", "danger")
            return redirect(request.url)

        output_kg = Decimal(str(total_carcass_weight_kg))

        yield_record = ProcessingYield(
            processing_batch_id=batch.id,
            total_carcass_weight_kg=output_kg,
            parts_included_in_batch_sale=parts_included,
            parts_sold_separately=parts_sold_separately,
            parts_notes=parts_notes,
            recorded_by_user_id=current_user.id,
        )

        processed_count = 0

        for animal in animals_in_processing_batch(batch):
            current_status = (animal.status or "").strip().lower()

            if current_status in ("aggregated", "processing"):
                animal.status = "processed"

                if hasattr(animal, "processed_at"):
                    animal.processed_at = datetime.utcnow()

                if hasattr(animal, "processed_by_user_id"):
                    animal.processed_by_user_id = current_user.id

                processed_count += 1

        db.session.add(yield_record)

        existing_lot = InventoryLot.query.filter_by(
            processing_batch_id=batch.id
        ).first()

        if existing_lot:
            existing_lot.quantity_kg = output_kg
            existing_lot.available_kg = output_kg
            existing_lot.unit = "kg"
            existing_lot.status = "available"
        else:
            inventory_lot = InventoryLot(
                processing_batch_id=batch.id,
                quantity_kg=output_kg,
                available_kg=output_kg,
                unit="kg",
                status="available",
            )
            db.session.add(inventory_lot)

        if not commit_or_rollback("Record processing yield and create inventory lot"):
            return redirect(request.url)

        flash(
            f"Processing yield recorded successfully. "
            f"{processed_count} animals marked as processed and inventory lot updated.",
            "success",
        )

        return redirect(url_for("invoices.new_invoice", batch_id=batch.id))

    return render_template(
        "processing/yield_add.html",
        batch=batch,
        current_year=datetime.utcnow().year,
    )

@processing_bp.route("/processing/<int:batch_id>/sale", methods=["GET", "POST"])
@admin_required
def record_processing_batch_sale(batch_id):
    flash(
        "Batch sale is now handled via signed contracts. Use 'Tender Sale / Issue Invoice' from Contracts.",
        "warning",
    )
    return redirect(url_for("contracts.list_contracts"))

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

@processing_bp.route("/invoices")
@admin_required
def list_invoices():
    invoices = (
        Invoice.query
        .order_by(Invoice.issue_date.desc(), Invoice.id.desc())
        .all()
    )

    return render_template(
        "invoices/list.html",
        invoices=invoices,
        current_year=datetime.utcnow().year,
        safe_enum_value=safe_enum_value,
    )

@processing_bp.route("/invoices/<int:invoice_id>")
@admin_required
def view_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    buyer = Buyer.query.get_or_404(invoice.buyer_id)
    items = InvoiceItem.query.filter_by(invoice_id=invoice.id).all()
    pipeline_case = PipelineCase.query.filter_by(invoice_id=invoice.id).first()
    sale = invoice.sale
    legacy_sale = getattr(invoice, "legacy_sale", None)

    contract = invoice.contract or (sale.contract if sale else None)
    batch = invoice.commercial_processing_batch

    signed_doc = None
    if contract:
        signed_doc = next(
            (
                d for d in contract.documents
                if d.document_type in {"signed_contract", "executed_contract"}
            ),
            None,
        )

    amount_paid = Decimal("0.00")
    balance_due = Decimal(str(invoice.total or 0))
    currency = "USD"

    if sale:
        currency = sale.currency or "USD"
        amount_paid = sum(Decimal(str(p.amount or 0)) for p in sale.payments)
        balance_due = max(Decimal(str(invoice.total or 0)) - amount_paid, Decimal("0.00"))

    return render_template(
        "invoices/invoice_view.html",
        invoice=invoice,
        buyer=buyer,
        items=items,
        sale=sale,
        legacy_sale=legacy_sale,
        contract=contract,
        batch=batch,
        signed_doc=signed_doc,
        pipeline_case=pipeline_case,
        amount_paid=amount_paid,
        balance_due=balance_due,
        currency=currency,
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

