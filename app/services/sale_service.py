from __future__ import annotations

from decimal import Decimal

from app.models import Sale


def generate_sale_number() -> str:
    last_sale = (
        Sale.query
        .order_by(Sale.id.desc())
        .first()
    )

    next_id = 1 if not last_sale else last_sale.id + 1
    return f"SAL-{next_id:05d}"


def calculate_sale_totals(sale: Sale) -> Sale:
    subtotal = Decimal("0.00")

    for item in sale.items:
        item.line_total = Decimal(item.quantity or 0) * Decimal(item.unit_price or 0)
        subtotal += item.line_total

    sale.subtotal = subtotal
    sale.discount = Decimal(sale.discount or 0)
    sale.tax_amount = Decimal(sale.tax_amount or 0)
    sale.total_amount = subtotal - sale.discount + sale.tax_amount
    sale.prepaid_amount = Decimal(sale.prepaid_amount or 0)
    sale.amount_paid = sum(Decimal(p.amount or 0) for p in sale.payments)
    sale.balance_due = sale.total_amount - sale.prepaid_amount - sale.amount_paid

    if sale.balance_due <= 0:
        sale.payment_status = "paid"
    elif sale.amount_paid > 0 or sale.prepaid_amount > 0:
        sale.payment_status = "partially_paid"
    else:
        sale.payment_status = "unpaid"

    return sale