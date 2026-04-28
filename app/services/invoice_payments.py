from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.extensions import db
from app.models import Invoice, InvoicePayment, InvoiceStatus


def money(value) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")


def next_receipt_number() -> str:
    last = InvoicePayment.query.order_by(InvoicePayment.id.desc()).first()
    next_id = (last.id + 1) if last else 1
    return f"RCT-2026-{next_id:05d}"


def total_invoice_payments(invoice: Invoice) -> Decimal:
    return money(sum(money(payment.amount) for payment in invoice.payments))


def recalculate_invoice_payment_status(invoice: Invoice) -> Invoice:
    total_paid = total_invoice_payments(invoice)
    total = money(invoice.total)

    invoice.deposit_paid = total_paid
    invoice.balance = money(total - total_paid)

    if invoice.balance <= 0 and total > 0:
        invoice.balance = Decimal("0.00")
        invoice.status = InvoiceStatus.PAID
    elif total_paid > 0:
        invoice.status = InvoiceStatus.PARTIALLY_PAID
    else:
        invoice.status = InvoiceStatus.ISSUED

    return invoice


def record_invoice_payment(
    invoice: Invoice,
    amount,
    method: str | None = None,
    reference: str | None = None,
    notes: str | None = None,
) -> InvoicePayment:
    amount = money(amount)

    if amount <= 0:
        raise ValueError("Payment amount must be greater than zero.")

    current_balance = money(invoice.balance)

    if current_balance <= 0:
        raise ValueError("This invoice is already fully paid.")

    if amount > current_balance:
        raise ValueError(
            f"Payment cannot exceed balance due. Balance is {invoice.currency or 'USD'} {current_balance:,.2f}."
        )

    payment = InvoicePayment(
        receipt_number=next_receipt_number(),
        invoice_id=invoice.id,
        amount=amount,
        method=(method or "").strip() or None,
        reference=(reference or "").strip() or None,
        notes=(notes or "").strip() or None,
    )

    db.session.add(payment)
    db.session.flush()

    recalculate_invoice_payment_status(invoice)

    return payment