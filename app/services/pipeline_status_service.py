from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import PipelineCase, PipelineEvent, Contract, Sale, Invoice

ZERO = Decimal("0.00")


class PipelineStatusService:
    @staticmethod
    def recompute_case(case: PipelineCase, actor_user_id: int | None = None, commit: bool = True) -> PipelineCase:
        contract = case.contract
        sale = case.sale
        invoice = case.invoice

        output_qty = Decimal(str(case.output_qty or 0))
        sold_qty = PipelineStatusService._sold_qty(sale, case)
        invoiced_amount = PipelineStatusService._invoice_amount(invoice, sale)
        paid_amount = PipelineStatusService._paid_amount(sale)
        outstanding_amount = max(invoiced_amount - paid_amount, ZERO)

        authorization_status, auth_reason = PipelineStatusService._authorization_status(contract, sale)
        payment_status = PipelineStatusService._payment_status(invoice, paid_amount, invoiced_amount)
        delivery_status = PipelineStatusService._delivery_status(case)

        current_stage, current_status, next_action, next_action_label, blocking_reason = (
            PipelineStatusService._main_status(
                contract=contract,
                sale=sale,
                invoice=invoice,
                authorization_status=authorization_status,
                payment_status=payment_status,
                delivery_status=delivery_status,
                auth_reason=auth_reason,
                output_qty=output_qty,
            )
        )

        health_status = PipelineStatusService._health_status(
            current_status=current_status,
            payment_status=payment_status,
            delivery_status=delivery_status,
            blocking_reason=blocking_reason,
        )

        case.current_stage = current_stage
        case.current_status = current_status
        case.authorization_status = authorization_status
        case.payment_status = payment_status
        case.delivery_status = delivery_status
        case.health_status = health_status
        case.next_action = next_action
        case.next_action_label = next_action_label
        case.blocking_reason = blocking_reason
        case.output_qty = output_qty
        case.sold_qty = sold_qty
        case.invoiced_amount = invoiced_amount
        case.paid_amount = paid_amount
        case.outstanding_amount = outstanding_amount
        case.currency = getattr(sale, "currency", None) or getattr(contract, "currency", None) or case.currency
        case.is_closed = current_status == "closed"

        db.session.add(case)
        PipelineStatusService.log_event(
            case=case,
            event_type="status_recomputed",
            actor_user_id=actor_user_id,
            message=f"Pipeline recomputed to {current_status}",
            metadata_json={
                "current_stage": current_stage,
                "current_status": current_status,
                "authorization_status": authorization_status,
                "payment_status": payment_status,
                "delivery_status": delivery_status,
                "health_status": health_status,
                "next_action": next_action,
            },
        )

        if commit:
            db.session.commit()

        return case

    @staticmethod
    def _authorization_status(contract: Contract | None, sale: Sale | None) -> tuple[str, str | None]:
        if not contract:
            return "pending", "No contract linked."

        payment_security_type = (contract.payment_security_type or "none").lower()
        release_mode = (contract.processing_release_mode or "manual_approval").lower()

        sale_total = Decimal(str(getattr(sale, "total_amount", 0) or 0)) if sale else ZERO
        sale_paid = Decimal(str(getattr(sale, "amount_paid", 0) or 0)) if sale else ZERO

        if sale and sale_total > ZERO and sale_paid >= sale_total:
            return "satisfied", "Sale fully paid."

        if release_mode == "manual_approval":
            if sale and sale.processing_authorized:
                return "satisfied", "Sale marked as processing-authorized."
            return "pending", "Awaiting manual processing approval."

        if payment_security_type == "none" and not contract.lc_required and not contract.prepayment_required:
            return "not_required", None

        required_prepayment = Decimal(str(contract.required_prepayment_amount or 0))

        if payment_security_type == "prepayment" or contract.prepayment_required:
            if required_prepayment <= ZERO and sale_paid > ZERO:
                return "satisfied", "Payment received."
            if required_prepayment > ZERO and sale_paid >= required_prepayment:
                return "satisfied", "Required prepayment received."
            return "pending", "Required prepayment not yet received."

        if payment_security_type == "lc" or contract.lc_required:
            if (contract.lc_status or "").lower() == "confirmed":
                return "satisfied", "LC confirmed."
            return "pending", "Awaiting LC confirmation."

        if payment_security_type == "mixed":
            if required_prepayment > ZERO and sale_paid >= required_prepayment:
                return "satisfied", "Required prepayment received."
            if (contract.lc_status or "").lower() == "confirmed":
                return "satisfied", "LC confirmed."
            return "pending", "Awaiting prepayment or LC confirmation."

        return "pending", "Authorization not yet satisfied."

    @staticmethod
    def _invoice_amount(invoice: Invoice | None, sale: Sale | None) -> Decimal:
        if invoice:
            return Decimal(str(invoice.total or 0))
        if sale:
            return Decimal(str(sale.total_amount or 0))
        return ZERO

    @staticmethod
    def _paid_amount(sale: Sale | None) -> Decimal:
        if sale:
            return Decimal(str(sale.amount_paid or 0))
        return ZERO

    @staticmethod
    def _sold_qty(sale: Sale | None, case: PipelineCase | None = None) -> Decimal:
        if not sale:
            return ZERO

        if case and case.output_qty:
            return Decimal(str(case.output_qty or 0))

        contract = getattr(sale, "contract", None)
        if contract and contract.contracted_quantity_kg:
            return Decimal(str(contract.contracted_quantity_kg or 0))

        return ZERO

    @staticmethod
    def _payment_status(invoice: Invoice | None, paid_amount: Decimal, invoiced_amount: Decimal) -> str:
        if invoiced_amount <= ZERO and paid_amount <= ZERO:
            return "none"

        if paid_amount >= invoiced_amount:
            return "paid"

        if paid_amount > ZERO:
            if invoice and invoice.due_date and invoice.due_date < date.today():
                return "overdue"
            return "partial"

        if invoice and invoice.due_date and invoice.due_date < date.today():
            return "overdue"

        return "pending"

    @staticmethod
    def _delivery_status(case: PipelineCase) -> str:
        if not case.deliveries:
            return "not_started"

        statuses = {delivery.status for delivery in case.deliveries}

        if "cancelled" in statuses:
            return "cancelled"
        if "delayed" in statuses:
            return "delayed"
        if "received" in statuses:
            return "received"
        if "delivered" in statuses:
            return "delivered"
        if "in_transit" in statuses:
            return "in_transit"
        if "dispatched" in statuses:
            return "dispatched"

        return "planned"

    @staticmethod
    def _main_status(
        contract: Contract | None,
        sale: Sale | None,
        invoice: Invoice | None,
        authorization_status: str,
        payment_status: str,
        delivery_status: str,
        auth_reason: str | None,
        output_qty: Decimal,
    ) -> tuple[str, str, str, str | None, str | None]:
        if not contract and not sale:
            return "sourcing", "sourcing", "capture_source", "Capture source/procurement records", "No contract or sale linked."

        if output_qty <= ZERO:
            return "processing", "processing", "capture_yield", "Capture processing output", None

        if not contract:
            return "commercial", "commercial_pending", "create_contract", "Create contract", "No contract linked."

        contract_status = (contract.status or "").lower()

        if contract_status in {"draft", "created"}:
            return "commercial", "commercial_pending", "send_contract", "Send contract for signing", None

        if contract_status in {"sent", "pending_signature"}:
            return "commercial", "awaiting_signature", "follow_up_signature", "Follow up signature", None

        if contract_status not in {"signed", "active", "approved"}:
            return "exception", "exception", "review_exception", "Review contract state", f"Unexpected contract status: {contract.status}"

        if authorization_status not in {"satisfied", "not_required"}:
            if auth_reason and "LC" in auth_reason:
                return "commercial", "awaiting_authorization", "confirm_lc", "Confirm LC", auth_reason
            return "commercial", "awaiting_authorization", "record_prepayment", "Record prepayment", auth_reason

        if not sale:
            return "sale", "sale_ready", "create_sale", "Create sale", None

        if not invoice:
            return "invoicing", "awaiting_invoice", "generate_invoice", "Generate invoice", None

        if payment_status in {"none", "pending", "partial", "overdue"}:
            return "payment", "partially_paid" if payment_status == "partial" else "invoiced", "record_payment", "Record payment", "Outstanding amount remains."

        if delivery_status in {"not_started", "planned"}:
            return "fulfillment", "paid", "dispatch_delivery", "Dispatch delivery", None

        if delivery_status in {"dispatched", "in_transit", "delivered"}:
            return "fulfillment", "in_delivery", "confirm_delivery", "Confirm delivery", None

        if delivery_status == "received":
            return "closure", "completed", "close_case", "Close pipeline case", None

        if delivery_status == "closed":
            return "closure", "closed", "none", None, None

        return "exception", "exception", "review_exception", "Review delivery state", f"Unexpected delivery status: {delivery_status}"

    @staticmethod
    def _health_status(current_status: str, payment_status: str, delivery_status: str, blocking_reason: str | None) -> str:
        if current_status in {"completed", "closed"}:
            return "blue"
        if current_status == "exception":
            return "red"
        if payment_status == "overdue":
            return "red"
        if delivery_status == "delayed":
            return "red"
        if blocking_reason and current_status not in {"sourcing", "commercial_pending"}:
            return "red"
        if current_status in {"awaiting_signature", "awaiting_authorization", "invoiced", "partially_paid"}:
            return "amber"
        return "green"

    @staticmethod
    def log_event(
        case: PipelineCase,
        event_type: str,
        actor_user_id: int | None = None,
        message: str | None = None,
        metadata_json: dict | None = None,
    ) -> PipelineEvent:
        event = PipelineEvent(
            pipeline_case_id=case.id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            message=message,
            metadata_json=metadata_json or {},
        )
        db.session.add(event)
        return event