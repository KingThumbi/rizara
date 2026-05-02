# app/utils/packing_list_pdf.py
from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from typing import Any

from flask import render_template
from weasyprint import HTML

from app.models import Document


def money_safe(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value))


def weight_safe(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value))


def cartons_from_weight(net_kg: Decimal, carton_size_kg: Decimal = Decimal("20")) -> int:
    if net_kg <= 0:
        return 0
    return max(1, int((net_kg / carton_size_kg).to_integral_value(rounding="ROUND_CEILING")))

def build_packing_list_context(document: Document) -> dict:
    sale = document.sale

    if not sale:
        raise ValueError("Packing List document must be linked to a Sale.")

    items = []
    total_cartons = 0
    total_net_kg = Decimal("0.00")
    total_gross_kg = Decimal("0.00")

    sale_items = getattr(sale, "items", []) or getattr(sale, "sale_items", []) or []

    for item in sale_items:
        lot = getattr(item, "inventory_lot", None)
        output = getattr(item, "processing_batch_output", None)

        product_name = (
            getattr(item, "product_name", None)
            or getattr(item, "description", None)
            or getattr(lot, "product_type", None)
            or getattr(output, "product_type", None)
            or "Processed Meat"
        )

        batch_number = (
            getattr(lot, "lot_number", None)
            or getattr(lot, "batch_number", None)
            or getattr(output, "batch_number", None)
            or getattr(output, "id", None)
            or "-"
        )

        net_kg = weight_safe(
            getattr(item, "quantity_kg", None)
            or getattr(item, "quantity", None)
            or getattr(item, "kg", None)
        )

        gross_kg = weight_safe(getattr(item, "gross_weight_kg", None))
        if gross_kg <= 0:
            gross_kg = net_kg * Decimal("1.05")

        cartons = getattr(item, "cartons", None)
        if cartons is None:
            cartons = cartons_from_weight(net_kg)

        cartons = int(cartons or 0)

        items.append(
            {
                "product_name": product_name,
                "description": getattr(item, "description", None) or "Frozen meat",
                "batch_number": str(batch_number),
                "cartons": cartons,
                "net_kg": net_kg,
                "gross_kg": gross_kg,
            }
        )

        total_cartons += cartons
        total_net_kg += net_kg
        total_gross_kg += gross_kg

    return {
        "document": document,
        "sale": sale,
        "buyer": document.buyer or getattr(sale, "buyer", None),
        "items": items,
        "total_cartons": total_cartons,
        "total_net_kg": total_net_kg,
        "total_gross_kg": total_gross_kg,
    }


def render_packing_list_html(document: Document) -> str:
    context = build_packing_list_context(document)
    return render_template("documents/packing_list_pdf.html", **context)


def generate_packing_list_pdf(document: Document) -> bytes:
    html = render_packing_list_html(document)

    pdf_buffer = BytesIO()
    HTML(string=html).write_pdf(pdf_buffer)

    return pdf_buffer.getvalue()