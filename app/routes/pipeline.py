from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from flask import Blueprint, jsonify, request



from datetime import date


from flask_login import login_required, current_user

from app.extensions import db
from app.models import PipelineCase, Sale, SalePayment, PipelineDelivery, utcnow_naive, Invoice
from app.services.pipeline_status_service import PipelineStatusService

pipeline_bp = Blueprint("pipeline", __name__, url_prefix="/api/pipeline")


def money(value):
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def serialize_case(case: PipelineCase) -> dict:
    return {
        "id": case.id,
        "case_number": case.case_number,
        "buyer": {
            "id": case.buyer.id if case.buyer else None,
            "name": case.buyer.name if case.buyer else None,
        },
        "contract": {
            "id": case.contract.id if case.contract else None,
            "contract_number": case.contract.contract_number if case.contract else None,
            "status": case.contract.status if case.contract else None,
        },
        "sale": {
            "id": case.sale.id if case.sale else None,
            "sale_number": case.sale.sale_number if case.sale else None,
            "status": case.sale.status if case.sale else None,
        },
        "invoice": {
            "id": case.invoice.id if case.invoice else None,
            "invoice_number": case.invoice.invoice_number if case.invoice else None,
            "status": case.invoice.status.value if case.invoice and hasattr(case.invoice.status, "value") else str(case.invoice.status) if case.invoice else None,
        },
        "statuses": {
            "stage": case.current_stage,
            "status": case.current_status,
            "authorization": case.authorization_status,
            "payment": case.payment_status,
            "delivery": case.delivery_status,
            "health": case.health_status,
        },
        "next_action": {
            "code": case.next_action,
            "label": case.next_action_label,
            "blocking_reason": case.blocking_reason,
        },
        "metrics": {
            "output_qty": money(case.output_qty),
            "sold_qty": money(case.sold_qty),
            "invoiced_amount": money(case.invoiced_amount),
            "paid_amount": money(case.paid_amount),
            "outstanding_amount": money(case.outstanding_amount),
            "currency": case.currency,
        },
        "dates": {
            "created_at": case.created_at.isoformat() if case.created_at else None,
            "updated_at": case.updated_at.isoformat() if case.updated_at else None,
            "closed_at": case.closed_at.isoformat() if case.closed_at else None,
        },
    }


@pipeline_bp.get("/dashboard")
@login_required
def dashboard():
    status = request.args.get("status")
    stage = request.args.get("stage")
    health = request.args.get("health")
    buyer_id = request.args.get("buyer_id", type=int)

    query = PipelineCase.query

    if status:
        query = query.filter(PipelineCase.current_status == status)

    if stage:
        query = query.filter(PipelineCase.current_stage == stage)

    if health:
        query = query.filter(PipelineCase.health_status == health)

    if buyer_id:
        query = query.filter(PipelineCase.buyer_id == buyer_id)

    cases = query.order_by(PipelineCase.updated_at.desc()).all()

    grouped_by_stage = defaultdict(list)
    grouped_by_status = defaultdict(list)

    total_output_qty = Decimal("0")
    total_sold_qty = Decimal("0")
    total_invoiced = Decimal("0")
    total_paid = Decimal("0")
    total_outstanding = Decimal("0")

    for case in cases:
        item = serialize_case(case)

        grouped_by_stage[case.current_stage].append(item)
        grouped_by_status[case.current_status].append(item)

        total_output_qty += case.output_qty or Decimal("0")
        total_sold_qty += case.sold_qty or Decimal("0")
        total_invoiced += case.invoiced_amount or Decimal("0")
        total_paid += case.paid_amount or Decimal("0")
        total_outstanding += case.outstanding_amount or Decimal("0")

    action_queue = [
        serialize_case(case)
        for case in cases
        if case.next_action and case.next_action != "none" and case.current_status not in {"closed", "completed"}
    ]

    exceptions = [
        serialize_case(case)
        for case in cases
        if case.current_status == "exception" or case.health_status == "red"
    ]

    return jsonify(
        {
            "ok": True,
            "summary": {
                "total_cases": len(cases),
                "active_cases": len([c for c in cases if not c.is_closed]),
                "closed_cases": len([c for c in cases if c.is_closed]),
                "exception_cases": len(exceptions),
                "total_output_qty": money(total_output_qty),
                "total_sold_qty": money(total_sold_qty),
                "total_invoiced_amount": money(total_invoiced),
                "total_paid_amount": money(total_paid),
                "total_outstanding_amount": money(total_outstanding),
            },
            "grouped_by_stage": dict(grouped_by_stage),
            "grouped_by_status": dict(grouped_by_status),
            "action_queue": action_queue[:20],
            "exceptions": exceptions[:20],
            "cases": [serialize_case(case) for case in cases],
        }
    )


@pipeline_bp.get("/cases")
@login_required
def list_cases():
    cases = PipelineCase.query.order_by(PipelineCase.updated_at.desc()).all()

    return jsonify(
        {
            "ok": True,
            "count": len(cases),
            "items": [serialize_case(case) for case in cases],
        }
    )


@pipeline_bp.get("/cases/<int:case_id>")
@login_required
def get_case(case_id: int):
    case = PipelineCase.query.get_or_404(case_id)

    events = [
        {
            "id": event.id,
            "event_type": event.event_type,
            "message": event.message,
            "metadata": event.metadata_json or {},
            "actor_user_id": event.actor_user_id,
            "event_at": event.event_at.isoformat() if event.event_at else None,
        }
        for event in case.events
    ]

    deliveries = [
        {
            "id": delivery.id,
            "delivery_number": delivery.delivery_number,
            "status": delivery.status,
            "destination": delivery.destination,
            "shipping_mode": delivery.shipping_mode,
            "quantity_kg": money(delivery.quantity_kg),
            "dispatch_date": delivery.dispatch_date.isoformat() if delivery.dispatch_date else None,
            "delivery_date": delivery.delivery_date.isoformat() if delivery.delivery_date else None,
            "shipping_docs_uploaded": delivery.shipping_docs_uploaded,
            "proof_of_delivery_uploaded": delivery.proof_of_delivery_uploaded,
            "notes": delivery.notes,
        }
        for delivery in case.deliveries
    ]

    return jsonify(
        {
            "ok": True,
            "case": serialize_case(case),
            "events": events,
            "deliveries": deliveries,
        }
    )

@pipeline_bp.post("/cases/<int:case_id>/mark-contract-signed")
@login_required
def mark_contract_signed(case_id: int):
    case = PipelineCase.query.get_or_404(case_id)

    if not case.contract:
        return jsonify({"ok": False, "error": "No contract linked."}), 400

    case.contract.status = "signed"
    case.contract.signed_at = utcnow_naive()

    db.session.add(case.contract)
    db.session.commit()

    PipelineStatusService.recompute_case(case, actor_user_id=current_user.id)

    return jsonify({"ok": True, "case": serialize_case(case)})


@pipeline_bp.post("/cases/<int:case_id>/create-sale")
@login_required
def create_sale(case_id: int):
    case = PipelineCase.query.get_or_404(case_id)

    if not case.contract:
        return jsonify({"ok": False, "error": "No contract linked."}), 400

    if case.sale:
        return jsonify({"ok": False, "error": "Sale already exists."}), 400

    data = request.get_json(silent=True) or {}

    total_amount = Decimal(str(data.get("total_amount") or case.contract.contracted_value or 0))
    currency = data.get("currency") or case.contract.currency or "USD"

    if total_amount <= 0:
        return jsonify({"ok": False, "error": "Sale total amount must be greater than zero."}), 400

    sale_number = f"SAL-{date.today().strftime('%Y%m%d')}-{case.id:04d}"
    customer_id = getattr(case.contract, "customer_id", None) or case.contract.buyer_id

    try:
        sale = Sale(
            sale_number=sale_number,
            contract_id=case.contract.id,
            customer_id=customer_id,
            buyer_id=case.contract.buyer_id,
            sale_date=date.today(),
            invoice_type="commercial",
            status="draft",
            currency=currency,
            subtotal=total_amount,
            discount=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            total_amount=total_amount,
            prepaid_amount=Decimal("0.00"),
            amount_paid=Decimal("0.00"),
            balance_due=total_amount,
            payment_status="unpaid",
            processing_authorized=False,
            created_by_user_id=current_user.id,
        )

        db.session.add(sale)
        db.session.flush()

        case.sale_id = sale.id
        case.buyer_id = sale.buyer_id
        case.currency = sale.currency
        case.invoiced_amount = total_amount
        case.outstanding_amount = total_amount

        db.session.add(case)

        PipelineStatusService.recompute_case(
            case,
            actor_user_id=current_user.id,
            commit=False,
        )

        db.session.commit()

        return jsonify({
            "ok": True,
            "sale_id": sale.id,
            "case": serialize_case(case),
        })

    except Exception as exc:
        db.session.rollback()
        return jsonify({
            "ok": False,
            "error": f"Could not create sale: {str(exc)}",
        }), 500

@pipeline_bp.post("/cases/<int:case_id>/record-payment")
@login_required
def record_payment(case_id: int):
    case = PipelineCase.query.get_or_404(case_id)

    if not case.sale:
        return jsonify({"ok": False, "error": "Create a sale first."}), 400

    data = request.get_json(silent=True) or {}

    amount = Decimal(str(data.get("amount") or 0))
    if amount <= 0:
        return jsonify({"ok": False, "error": "Payment amount must be greater than zero."}), 400

    current_paid = Decimal(str(case.sale.amount_paid or 0))
    sale_total = Decimal(str(case.sale.total_amount or 0))
    new_paid_total = current_paid + amount

    if new_paid_total > sale_total:
        return jsonify({
            "ok": False,
            "error": f"Payment exceeds sale total. Outstanding balance is {sale_total - current_paid}.",
        }), 400

    try:
        payment = SalePayment(
            sale_id=case.sale.id,
            payment_date=date.today(),
            payment_type=data.get("payment_type") or "partial_payment",
            payment_method=data.get("payment_method") or "bank_transfer",
            amount=amount,
            reference_number=data.get("reference_number"),
            notes=data.get("notes"),
            created_by_user_id=current_user.id,
        )

        case.sale.amount_paid = new_paid_total
        case.sale.balance_due = max(sale_total - new_paid_total, Decimal("0.00"))

        if case.sale.balance_due <= 0:
            case.sale.payment_status = "paid"
            case.sale.status = "paid"
        elif new_paid_total > 0:
            case.sale.payment_status = "partial"
            case.sale.status = "partial"

        db.session.add(payment)
        db.session.add(case.sale)

        PipelineStatusService.recompute_case(
            case,
            actor_user_id=current_user.id,
            commit=False,
        )

        db.session.commit()

        return jsonify({
            "ok": True,
            "payment_id": payment.id,
            "case": serialize_case(case),
        })

    except Exception as exc:
        db.session.rollback()
        return jsonify({
            "ok": False,
            "error": f"Could not record payment: {str(exc)}",
        }), 500       

@pipeline_bp.post("/cases/<int:case_id>/dispatch-delivery")
@login_required
def dispatch_delivery(case_id: int):
    case = PipelineCase.query.get_or_404(case_id)

    if not case.sale:
        return jsonify({"ok": False, "error": "Create a sale first."}), 400

    data = request.get_json(silent=True) or {}

    delivery = PipelineDelivery(
        pipeline_case_id=case.id,
        sale_id=case.sale.id,
        delivery_number=data.get("delivery_number") or f"DEL-{date.today().strftime('%Y%m%d')}-{case.id:04d}",
        destination=data.get("destination"),
        shipping_mode=data.get("shipping_mode") or "road",
        quantity_kg=Decimal(str(data.get("quantity_kg") or case.sold_qty or case.output_qty or 0)),
        dispatch_date=date.today(),
        status="dispatched",
        notes=data.get("notes"),
    )

    db.session.add(delivery)
    db.session.commit()

    PipelineStatusService.recompute_case(case, actor_user_id=current_user.id)

    return jsonify({"ok": True, "delivery_id": delivery.id, "case": serialize_case(case)})    

@pipeline_bp.post("/cases/<int:case_id>/generate-invoice")
@login_required
def generate_invoice(case_id: int):
    case = PipelineCase.query.get_or_404(case_id)

    if not case.sale:
        return jsonify({"ok": False, "error": "Create a sale first."}), 400

    if case.invoice:
        return jsonify({"ok": False, "error": "Invoice already exists."}), 400

    sale_total = Decimal(str(case.sale.total_amount or 0))
    if sale_total <= 0:
        return jsonify({"ok": False, "error": "Sale amount must be greater than zero."}), 400

    invoice_number = f"INV-{date.today().strftime('%Y%m%d')}-{case.id:04d}"

    try:
        invoice = Invoice(
            invoice_number=invoice_number,
            buyer_id=case.sale.buyer_id,
            issue_date=date.today(),
            due_date=date.today(),
            status="issued",
            issued_at=utcnow_naive(),
            subtotal=sale_total,
            tax=Decimal("0.00"),
            total=sale_total,
            notes=f"Generated from pipeline case {case.case_number}",
            terms="Payment as per contract.",
            issued_by_user_id=current_user.id,
        )

        db.session.add(invoice)
        db.session.flush()

        case.invoice_id = invoice.id
        case.invoiced_amount = sale_total
        case.outstanding_amount = max(sale_total - Decimal(str(case.sale.amount_paid or 0)), Decimal("0.00"))

        db.session.add(case)

        PipelineStatusService.recompute_case(
            case,
            actor_user_id=current_user.id,
            commit=False,
        )

        db.session.commit()

        return jsonify({
            "ok": True,
            "invoice_id": invoice.id,
            "case": serialize_case(case),
        })

    except Exception as exc:
        db.session.rollback()
        return jsonify({
            "ok": False,
            "error": f"Could not generate invoice: {str(exc)}",
        }), 500

@pipeline_bp.post("/cases/<int:case_id>/confirm-delivery")
@login_required
def confirm_delivery(case_id: int):
    case = PipelineCase.query.get_or_404(case_id)

    if not case.deliveries:
        return jsonify({"ok": False, "error": "No delivery found."}), 400

    delivery = case.deliveries[0]
    delivery.status = "received"
    delivery.delivery_date = date.today()
    delivery.proof_of_delivery_uploaded = True

    db.session.add(delivery)

    PipelineStatusService.recompute_case(
        case,
        actor_user_id=current_user.id,
        commit=False,
    )

    db.session.commit()

    return jsonify({"ok": True, "case": serialize_case(case)})        

@pipeline_bp.post("/cases/<int:case_id>/close")
@login_required
def close_case(case_id: int):
    case = PipelineCase.query.get_or_404(case_id)

    if case.payment_status != "paid":
        return jsonify({"ok": False, "error": "Cannot close case before payment is complete."}), 400

    if case.delivery_status not in {"received", "closed"}:
        return jsonify({"ok": False, "error": "Cannot close case before delivery is received."}), 400

    case.current_stage = "closure"
    case.current_status = "closed"
    case.delivery_status = "closed"
    case.health_status = "blue"
    case.next_action = "none"
    case.next_action_label = None
    case.blocking_reason = None
    case.is_closed = True
    case.closed_at = utcnow_naive()

    for delivery in case.deliveries:
        delivery.status = "closed"
        db.session.add(delivery)

    PipelineStatusService.log_event(
        case=case,
        event_type="case_closed",
        actor_user_id=current_user.id,
        message=f"Pipeline case {case.case_number} closed.",
    )

    db.session.add(case)
    db.session.commit()

    return jsonify({"ok": True, "case": serialize_case(case)})