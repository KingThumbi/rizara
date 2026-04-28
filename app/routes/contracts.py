# app/routes/contracts.py

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from app.utils.time_helpers import utcnow_naive

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import (
    Buyer,
    CommercialProcessingBatch,
    Contract,
    ContractDocument,
    ContractItem,
    Sale,
    SaleItem,
    SalePayment,
)
from app.services.contract_service import (
    calculate_contract_totals,
    can_activate_contract,
    can_approve_contract,
    can_mark_signed,
    can_submit_contract_for_review,
    generate_contract_number,
)
from app.services.sale_service import (
    calculate_sale_totals,
    generate_sale_number,
)

bp = Blueprint("contracts", __name__, url_prefix="/contracts")

@bp.get("")
@login_required
def list_contracts():
    status = (request.args.get("status") or "").strip()
    buyer_id = request.args.get("buyer_id", type=int)
    q = (request.args.get("q") or "").strip()

    # Used when selecting a contract to link a processing batch.
    select_for_batch = request.args.get("select_for_batch", type=int)

    query = Contract.query.order_by(Contract.created_at.desc())

    if status:
        query = query.filter(Contract.status == status)

    if buyer_id:
        query = query.filter(Contract.buyer_id == buyer_id)

    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                Contract.contract_number.ilike(like),
                Contract.destination_country.ilike(like),
                Contract.product_type.ilike(like),
            )
        )

    contracts = query.all()
    buyers = Buyer.query.order_by(Buyer.name.asc()).all()

    return render_template(
        "contracts/list.html",
        contracts=contracts,
        buyers=buyers,
        selected_status=status,
        selected_buyer_id=buyer_id,
        q=q,
        select_for_batch=select_for_batch,
    )

@bp.get("/new")
@login_required
def new_contract():
    buyers = Buyer.query.order_by(Buyer.name.asc()).all()
    return render_template(
        "contracts/form.html",
        contract=None,
        buyers=buyers,
        form_action=url_for("contracts.create_contract"),
    )


@bp.post("")
@login_required
def create_contract():
    buyer_id = request.form.get("buyer_id", type=int)
    contract_date = request.form.get("contract_date")
    delivery_date = request.form.get("delivery_date") or None

    if not buyer_id or not contract_date:
        flash("Buyer and contract date are required.", "danger")
        return redirect(url_for("contracts.new_contract"))

    contract = Contract(
        contract_number=generate_contract_number(),
        buyer_id=buyer_id,
        contract_date=contract_date,
        delivery_date=delivery_date,
        currency=(request.form.get("currency") or "USD").strip(),
        price_basis=(request.form.get("price_basis") or None),
        payment_terms=(request.form.get("payment_terms") or None),
        delivery_terms=(request.form.get("delivery_terms") or None),
        destination_country=(request.form.get("destination_country") or None),
        payment_security_type=(request.form.get("payment_security_type") or "none").strip(),
        prepayment_required=bool(request.form.get("prepayment_required")),
        required_prepayment_percent=request.form.get("required_prepayment_percent") or None,
        required_prepayment_amount=request.form.get("required_prepayment_amount") or None,
        lc_required=bool(request.form.get("lc_required")),
        lc_number=(request.form.get("lc_number") or None),
        lc_issuing_bank=(request.form.get("lc_issuing_bank") or None),
        lc_status=(request.form.get("lc_status") or None),
        processing_release_mode=(request.form.get("processing_release_mode") or "manual_approval").strip(),
        contracted_quantity_kg=request.form.get("contracted_quantity_kg") or None,
        contracted_value=request.form.get("contracted_value") or None,
        product_type=(request.form.get("product_type") or None),
        quality_spec=(request.form.get("quality_spec") or None),
        notes=(request.form.get("notes") or None),
        created_by_user_id=getattr(current_user, "id", None),
    )

    db.session.add(contract)
    db.session.commit()

    flash("Contract created successfully.", "success")
    return redirect(url_for("contracts.view_contract", contract_id=contract.id))


@bp.get("/<int:contract_id>")
@login_required
def view_contract(contract_id: int):
    contract = Contract.query.get_or_404(contract_id)
    summary = calculate_contract_totals(contract)

    return render_template(
        "contracts/detail.html",
        contract=contract,
        summary=summary,
    )


@bp.get("/<int:contract_id>/edit")
@login_required
def edit_contract(contract_id: int):
    contract = Contract.query.get_or_404(contract_id)
    buyers = Buyer.query.order_by(Buyer.name.asc()).all()

    return render_template(
        "contracts/form.html",
        contract=contract,
        buyers=buyers,
        form_action=url_for("contracts.update_contract", contract_id=contract.id),
    )


@bp.post("/<int:contract_id>/update")
@login_required
def update_contract(contract_id: int):
    contract = Contract.query.get_or_404(contract_id)

    if contract.status in {"fulfilled", "cancelled"}:
        flash("Finalized contracts cannot be edited.", "warning")
        return redirect(url_for("contracts.view_contract", contract_id=contract.id))

    contract.buyer_id = request.form.get("buyer_id", type=int)
    contract.contract_date = request.form.get("contract_date")
    contract.delivery_date = request.form.get("delivery_date") or None
    contract.currency = (request.form.get("currency") or "USD").strip()
    contract.price_basis = request.form.get("price_basis") or None
    contract.payment_terms = request.form.get("payment_terms") or None
    contract.delivery_terms = request.form.get("delivery_terms") or None
    contract.destination_country = request.form.get("destination_country") or None
    contract.payment_security_type = (request.form.get("payment_security_type") or "none").strip()
    contract.prepayment_required = bool(request.form.get("prepayment_required"))
    contract.required_prepayment_percent = request.form.get("required_prepayment_percent") or None
    contract.required_prepayment_amount = request.form.get("required_prepayment_amount") or None
    contract.lc_required = bool(request.form.get("lc_required"))
    contract.lc_number = request.form.get("lc_number") or None
    contract.lc_issuing_bank = request.form.get("lc_issuing_bank") or None
    contract.lc_status = request.form.get("lc_status") or None
    contract.processing_release_mode = (request.form.get("processing_release_mode") or "manual_approval").strip()
    contract.contracted_quantity_kg = request.form.get("contracted_quantity_kg") or None
    contract.contracted_value = request.form.get("contracted_value") or None
    contract.product_type = request.form.get("product_type") or None
    contract.quality_spec = request.form.get("quality_spec") or None
    contract.notes = request.form.get("notes") or None

    db.session.commit()

    flash("Contract updated successfully.", "success")
    return redirect(url_for("contracts.view_contract", contract_id=contract.id))


@bp.post("/<int:contract_id>/delete")
@login_required
def delete_contract(contract_id: int):
    contract = Contract.query.get_or_404(contract_id)

    if contract.sales or contract.processing_batches:
        flash("Cannot delete a contract already linked to batches or sales.", "danger")
        return redirect(url_for("contracts.view_contract", contract_id=contract.id))

    db.session.delete(contract)
    db.session.commit()

    flash("Contract deleted successfully.", "success")
    return redirect(url_for("contracts.list_contracts"))

@bp.post("/<int:contract_id>/items")
@login_required
def add_contract_item(contract_id: int):
    contract = Contract.query.get_or_404(contract_id)

    item = ContractItem(
        contract_id=contract.id,
        product_name=(request.form.get("product_name") or "").strip(),
        product_code=(request.form.get("product_code") or None),
        unit_of_measure=(request.form.get("unit_of_measure") or "kg").strip(),
        quantity=Decimal(request.form.get("quantity") or "0"),
        unit_price=Decimal(request.form.get("unit_price") or "0"),
        quality_spec=(request.form.get("quality_spec") or None),
        notes=(request.form.get("notes") or None),
    )
    item.total_price = item.quantity * item.unit_price

    db.session.add(item)
    db.session.commit()

    flash("Contract item added.", "success")
    return redirect(url_for("contracts.view_contract", contract_id=contract.id))


@bp.post("/<int:contract_id>/items/<int:item_id>/update")
@login_required
def update_contract_item(contract_id: int, item_id: int):
    contract = Contract.query.get_or_404(contract_id)
    item = ContractItem.query.filter_by(id=item_id, contract_id=contract.id).first_or_404()

    item.product_name = (request.form.get("product_name") or "").strip()
    item.product_code = request.form.get("product_code") or None
    item.unit_of_measure = (request.form.get("unit_of_measure") or "kg").strip()
    item.quantity = Decimal(request.form.get("quantity") or "0")
    item.unit_price = Decimal(request.form.get("unit_price") or "0")
    item.total_price = item.quantity * item.unit_price
    item.quality_spec = request.form.get("quality_spec") or None
    item.notes = request.form.get("notes") or None

    db.session.commit()

    flash("Contract item updated.", "success")
    return redirect(url_for("contracts.view_contract", contract_id=contract.id))


@bp.post("/<int:contract_id>/items/<int:item_id>/delete")
@login_required
def delete_contract_item(contract_id: int, item_id: int):
    contract = Contract.query.get_or_404(contract_id)
    item = ContractItem.query.filter_by(id=item_id, contract_id=contract.id).first_or_404()

    if item.sale_items:
        flash("Cannot delete a contract item already used in a sale.", "danger")
        return redirect(url_for("contracts.view_contract", contract_id=contract.id))

    db.session.delete(item)
    db.session.commit()

    flash("Contract item deleted.", "success")
    return redirect(url_for("contracts.view_contract", contract_id=contract.id))

def _contract_upload_dir(contract: Contract) -> Path:
    base = Path(current_app.instance_path) / "uploads" / "contracts" / contract.contract_number
    base.mkdir(parents=True, exist_ok=True)
    return base


@bp.post("/<int:contract_id>/documents")
@login_required
def upload_contract_document(contract_id: int):
    contract = Contract.query.get_or_404(contract_id)
    uploaded = request.files.get("document")

    if not uploaded or not uploaded.filename:
        flash("Please choose a file to upload.", "danger")
        return redirect(url_for("contracts.view_contract", contract_id=contract.id))

    safe_name = secure_filename(uploaded.filename)
    upload_dir = _contract_upload_dir(contract)
    save_path = upload_dir / safe_name
    uploaded.save(save_path)

    document = ContractDocument(
        contract_id=contract.id,
        document_type=(request.form.get("document_type") or "other").strip(),
        title=(request.form.get("title") or safe_name).strip(),
        file_path=str(save_path),
        original_filename=uploaded.filename,
        stored_filename=safe_name,
        mime_type=uploaded.mimetype,
        file_size=save_path.stat().st_size if save_path.exists() else None,
        notes=(request.form.get("notes") or None),
        uploaded_by_user_id=getattr(current_user, "id", None),
    )

    db.session.add(document)
    db.session.commit()

    flash("Document uploaded successfully.", "success")
    return redirect(url_for("contracts.view_contract", contract_id=contract.id))


@bp.get("/<int:contract_id>/documents/<int:document_id>/download")
@login_required
def download_contract_document(contract_id: int, document_id: int):
    contract = Contract.query.get_or_404(contract_id)
    document = ContractDocument.query.filter_by(
        id=document_id,
        contract_id=contract.id,
    ).first_or_404()

    return send_file(
        document.file_path,
        as_attachment=True,
        download_name=document.original_filename or document.stored_filename,
    )


@bp.post("/<int:contract_id>/documents/<int:document_id>/set-primary")
@login_required
def set_primary_contract_document(contract_id: int, document_id: int):
    contract = Contract.query.get_or_404(contract_id)
    document = ContractDocument.query.filter_by(
        id=document_id,
        contract_id=contract.id,
    ).first_or_404()

    ContractDocument.query.filter_by(contract_id=contract.id, is_primary=True).update(
        {"is_primary": False}
    )
    document.is_primary = True

    db.session.commit()

    flash("Primary contract document updated.", "success")
    return redirect(url_for("contracts.view_contract", contract_id=contract.id))


@bp.post("/<int:contract_id>/documents/<int:document_id>/delete")
@login_required
def delete_contract_document(contract_id: int, document_id: int):
    contract = Contract.query.get_or_404(contract_id)
    document = ContractDocument.query.filter_by(
        id=document_id,
        contract_id=contract.id,
    ).first_or_404()

    if contract.status in {"signed", "active", "partially_fulfilled", "fulfilled"}:
        flash("Documents cannot be deleted after contract signing/activation.", "danger")
        return redirect(url_for("contracts.view_contract", contract_id=contract.id))

    file_path = Path(document.file_path)
    if file_path.exists():
        file_path.unlink(missing_ok=True)

    db.session.delete(document)
    db.session.commit()

    flash("Document deleted.", "success")
    return redirect(url_for("contracts.view_contract", contract_id=contract.id))

@bp.post("/<int:contract_id>/submit-review")
@login_required
def submit_contract_for_review(contract_id: int):
    contract = Contract.query.get_or_404(contract_id)

    ok, message = can_submit_contract_for_review(contract)
    if not ok:
        flash(message, "danger")
        return redirect(url_for("contracts.view_contract", contract_id=contract.id))

    contract.status = "under_review"
    contract.submitted_for_review_at = utcnow_naive()

    db.session.commit()

    flash("Contract submitted for review.", "success")
    return redirect(url_for("contracts.view_contract", contract_id=contract.id))


@bp.post("/<int:contract_id>/approve")
@login_required
def approve_contract(contract_id: int):
    contract = Contract.query.get_or_404(contract_id)

    ok, message = can_approve_contract(contract)
    if not ok:
        flash(message, "danger")
        return redirect(url_for("contracts.view_contract", contract_id=contract.id))

    contract.status = "approved"
    contract.reviewed_at = utcnow_naive()
    contract.approved_at = utcnow_naive()
    contract.reviewed_by_user_id = getattr(current_user, "id", None)
    contract.approved_by_user_id = getattr(current_user, "id", None)

    db.session.commit()

    flash("Contract approved.", "success")
    return redirect(url_for("contracts.view_contract", contract_id=contract.id))


@bp.post("/<int:contract_id>/mark-sent")
@login_required
def mark_contract_sent(contract_id: int):
    contract = Contract.query.get_or_404(contract_id)

    if contract.status != "approved":
        flash("Only approved contracts can be marked as sent.", "danger")
        return redirect(url_for("contracts.view_contract", contract_id=contract.id))

    contract.status = "sent"
    db.session.commit()

    flash("Contract marked as sent.", "success")
    return redirect(url_for("contracts.view_contract", contract_id=contract.id))


@bp.post("/<int:contract_id>/mark-signed")
@login_required
def mark_contract_signed(contract_id: int):
    contract = Contract.query.get_or_404(contract_id)

    ok, message = can_mark_signed(contract)
    if not ok:
        flash(message, "danger")
        return redirect(url_for("contracts.view_contract", contract_id=contract.id))

    contract.status = "signed"
    contract.signed_at = utcnow_naive()

    db.session.commit()

    flash("Contract marked as signed.", "success")
    return redirect(url_for("contracts.view_contract", contract_id=contract.id))


@bp.post("/<int:contract_id>/activate")
@login_required
def activate_contract(contract_id: int):
    contract = Contract.query.get_or_404(contract_id)

    ok, message = can_activate_contract(contract)
    if not ok:
        flash(message, "danger")
        return redirect(url_for("contracts.view_contract", contract_id=contract.id))

    contract.status = "active"
    contract.activated_at = utcnow_naive()

    db.session.commit()

    flash("Contract activated.", "success")
    return redirect(url_for("contracts.view_contract", contract_id=contract.id))


@bp.post("/<int:contract_id>/cancel")
@login_required
def cancel_contract(contract_id: int):
    contract = Contract.query.get_or_404(contract_id)

    if contract.sales:
        flash("Cannot cancel a contract already linked to sales.", "danger")
        return redirect(url_for("contracts.view_contract", contract_id=contract.id))

    contract.status = "cancelled"
    contract.cancelled_at = utcnow_naive()
    contract.cancel_reason = request.form.get("cancel_reason") or None

    db.session.commit()

    flash("Contract cancelled.", "warning")
    return redirect(url_for("contracts.view_contract", contract_id=contract.id))

@bp.get("/<int:contract_id>/sales/new")
@login_required
def new_sale_from_contract(contract_id: int):
    contract = Contract.query.get_or_404(contract_id)
    summary = calculate_contract_totals(contract)

    if contract.status not in {"signed", "active", "partially_fulfilled"}:
        flash("Only signed or active contracts can create sales.", "danger")
        return redirect(url_for("contracts.view_contract", contract_id=contract.id))

    return render_template(
        "contracts/new_sale.html",
        contract=contract,
        summary=summary,
    )


@bp.post("/<int:contract_id>/sales")
@login_required
def create_sale_from_contract(contract_id: int):
    contract = Contract.query.get_or_404(contract_id)

    if contract.status not in {"signed", "active", "partially_fulfilled"}:
        flash("Only signed or active contracts can create sales.", "danger")
        return redirect(url_for("contracts.view_contract", contract_id=contract.id))

    sale = Sale(
        sale_number=generate_sale_number(),
        contract_id=contract.id,
        buyer_id=contract.buyer_id,
        sale_date=request.form.get("sale_date"),
        invoice_type=(request.form.get("invoice_type") or "commercial").strip(),
        status="draft",
        currency=contract.currency,
        notes=(request.form.get("notes") or None),
        created_by_user_id=getattr(current_user, "id", None),
    )
    db.session.add(sale)
    db.session.flush()

    item_ids = request.form.getlist("contract_item_id")
    quantities = request.form.getlist("quantity")
    unit_prices = request.form.getlist("unit_price")

    for idx, raw_item_id in enumerate(item_ids):
        if not raw_item_id:
            continue

        contract_item = ContractItem.query.filter_by(
            id=int(raw_item_id),
            contract_id=contract.id,
        ).first()

        if not contract_item:
            continue

        quantity = Decimal(quantities[idx] or "0")
        unit_price = Decimal(unit_prices[idx] or str(contract_item.unit_price))
        line_total = quantity * unit_price

        sale_item = SaleItem(
            sale_id=sale.id,
            contract_item_id=contract_item.id,
            product_name=contract_item.product_name,
            product_code=contract_item.product_code,
            quantity=quantity,
            unit_of_measure=contract_item.unit_of_measure,
            unit_price=unit_price,
            line_total=line_total,
        )
        db.session.add(sale_item)

    calculate_sale_totals(sale)
    db.session.commit()

    flash("Sale created from contract.", "success")
    return redirect(url_for("sales.view_sale", sale_id=sale.id))

@bp.route("/<int:contract_id>/tender-sale", methods=["GET", "POST"])
@login_required
def tender_sale(contract_id):
    from decimal import Decimal
    from datetime import date

    from app.models import (
        Contract,
        Sale,
        SaleItem,
        SalePayment,
        Invoice,
        InvoiceItem,
        InvoiceStatus,
        PipelineCase,
        CommercialProcessingBatch,
    )

    contract = Contract.query.get_or_404(contract_id)

    if contract.status not in {"signed", "active", "approved", "partially_fulfilled"}:
        flash("Only approved, signed, or active contracts can be invoiced.", "danger")
        return redirect(url_for("contracts.contract_detail", contract_id=contract.id))

    batches = CommercialProcessingBatch.query.filter_by(contract_id=contract.id).all()

    if request.method == "GET":
        return render_template(
            "contracts/tender_sale.html",
            contract=contract,
            batches=batches,
            currency_options=["USD", "AED", "SAR", "QAR", "EUR", "GBP", "KES"],
            current_year=date.today().year,
        )

    currency = request.form.get("currency") or contract.currency or "USD"
    batch_id = request.form.get("commercial_processing_batch_id") or None
    deposit_amount = Decimal(str(request.form.get("deposit_amount") or 0))
    deposit_reference = request.form.get("deposit_reference") or None
    deposit_method = request.form.get("deposit_method") or "bank_transfer"

    product_names = request.form.getlist("product_name[]")
    quantities = request.form.getlist("quantity[]")
    contract_prices = request.form.getlist("contract_unit_price[]")
    invoice_prices = request.form.getlist("invoice_unit_price[]")
    adjustment_reasons = request.form.getlist("price_adjustment_reason[]")

    if not product_names:
        flash("Add at least one invoice item.", "danger")
        return redirect(request.url)

    sale_number = f"SAL-{date.today().strftime('%Y%m%d')}-{contract.id:04d}"
    invoice_number = f"INV-{date.today().strftime('%Y%m%d')}-{contract.id:04d}"

    subtotal = Decimal("0.00")
    prepared_lines = []

    for i, product_name in enumerate(product_names):
        qty = Decimal(str(quantities[i] or 0))
        contract_price = Decimal(str(contract_prices[i] or 0))
        invoice_price = Decimal(str(invoice_prices[i] or 0))
        line_total = qty * invoice_price
        adjustment = invoice_price - contract_price
        reason = adjustment_reasons[i] if i < len(adjustment_reasons) else None

        if adjustment != 0 and not reason:
            flash("Price changes require a reason.", "danger")
            return redirect(request.url)

        subtotal += line_total

        prepared_lines.append({
            "product_name": product_name,
            "qty": qty,
            "contract_price": contract_price,
            "invoice_price": invoice_price,
            "adjustment": adjustment,
            "reason": reason,
            "line_total": line_total,
        })

    balance_due = max(subtotal - deposit_amount, Decimal("0.00"))

    sale = Sale(
        sale_number=sale_number,
        contract_id=contract.id,
        customer_id=contract.buyer_id,
        buyer_id=contract.buyer_id,
        sale_date=date.today(),
        invoice_type="commercial",
        status="partial" if deposit_amount > 0 else "draft",
        currency=currency,
        subtotal=subtotal,
        discount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        total_amount=subtotal,
        prepaid_amount=deposit_amount,
        amount_paid=deposit_amount,
        balance_due=balance_due,
        payment_status="partial" if deposit_amount > 0 else "unpaid",
        created_by_user_id=current_user.id,
    )

    db.session.add(sale)
    db.session.flush()

    invoice = Invoice(
        invoice_number=invoice_number,
        buyer_id=contract.buyer_id,
        sale_id=sale.id,
        contract_id=contract.id,
        commercial_processing_batch_id=int(batch_id) if batch_id else None,
        issue_date=date.today(),
        due_date=date.today(),
        status=InvoiceStatus.PAID if balance_due <= 0 else InvoiceStatus.ISSUED,
        issued_at=datetime.utcnow(),
        paid_at=datetime.utcnow() if balance_due <= 0 else None,
        subtotal=subtotal,
        tax=Decimal("0.00"),
        total=subtotal,
        terms=contract.payment_terms or "Payment as per signed contract.",
        notes="Invoice generated from signed contract tender-sale flow.",
        issued_by_user_id=current_user.id,
    )

    db.session.add(invoice)
    db.session.flush()

    for line in prepared_lines:
        sale_item = SaleItem(
            sale_id=sale.id,
            product_name=line["product_name"],
            quantity=line["qty"],
            unit_of_measure="kg",
            unit_price=line["invoice_price"],
            line_total=line["line_total"],
            notes=(
                f"Contract price: {currency} {line['contract_price']}/kg. "
                f"Invoice price: {currency} {line['invoice_price']}/kg. "
                f"Adjustment: {currency} {line['adjustment']}/kg. "
                f"Reason: {line['reason'] or '-'}"
            ),
        )

        invoice_item = InvoiceItem(
            invoice_id=invoice.id,
            description=(
                f"{line['product_name']} | Contract: {currency} {line['contract_price']}/kg "
                f"| Invoice: {currency} {line['invoice_price']}/kg"
                + (f" | Adjustment reason: {line['reason']}" if line["adjustment"] != 0 else "")
            ),
            quantity=line["qty"],
            unit_price=line["invoice_price"],
            line_total=line["line_total"],
        )

        db.session.add(sale_item)
        db.session.add(invoice_item)

    if deposit_amount > 0:
        payment = SalePayment(
            sale_id=sale.id,
            payment_date=date.today(),
            payment_type="prepayment",
            payment_method=deposit_method,
            amount=deposit_amount,
            reference_number=deposit_reference,
            notes="Deposit received upon signed contract.",
            created_by_user_id=current_user.id,
        )
        db.session.add(payment)

    case = PipelineCase.query.filter_by(contract_id=contract.id).first()
    if case:
        case.sale_id = sale.id
        case.invoice_id = invoice.id
        case.buyer_id = contract.buyer_id
        case.currency = currency
        case.invoiced_amount = subtotal
        case.paid_amount = deposit_amount
        case.outstanding_amount = balance_due
        db.session.add(case)

    db.session.commit()

    flash("Sale tendered and invoice issued successfully.", "success")
    return redirect(url_for("processing.view_invoice", invoice_id=invoice.id))

@bp.post("/<int:contract_id>/link-processing-batch/<int:batch_id>")
@login_required
def link_processing_batch(contract_id, batch_id):
    from app.models import Contract, CommercialProcessingBatch, ProcessingBatch

    contract = Contract.query.get_or_404(contract_id)
    legacy_batch = ProcessingBatch.query.get_or_404(batch_id)

    commercial_batch = CommercialProcessingBatch(
        batch_number=f"CPB-{legacy_batch.id}",
        contract_id=contract.id,
        status="processed",
        processing_date=legacy_batch.slaughter_date,
        source_type="legacy_processing_batch",
        source_reference_id=legacy_batch.id,
        output_qty=None,
        processing_authorized=True,
        authorization_status="approved",
        authorization_basis="linked_to_signed_contract",
        notes=f"Linked from legacy processing batch #{legacy_batch.id}.",
        created_by_user_id=current_user.id,
    )

    db.session.add(commercial_batch)
    db.session.commit()

    flash("Processing batch linked to contract successfully.", "success")
    return redirect(url_for("contracts.tender_sale", contract_id=contract.id))            