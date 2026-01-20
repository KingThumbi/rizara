# app/utils/invoice_pdf.py

from __future__ import annotations

import io
from datetime import datetime, date

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle


def _fmt_date(d):
    if not d:
        return "-"
    if isinstance(d, (datetime, date)):
        return d.strftime("%Y-%m-%d")
    return str(d)


def _money(v, currency="KES"):
    try:
        if v is None:
            return "-"
        return f"{currency} {float(v):,.2f}"
    except Exception:
        return f"{currency} {v}"


def _safe_enum_value(v):
    # Enum -> .value else raw
    try:
        return v.value
    except Exception:
        return v


def render_invoice_pdf(invoice) -> bytes:
    """
    Render an Invoice PDF (NO DB writes).
    Returns PDF bytes.
    """
    # Import inside function to avoid circular imports during app boot
    from app.models import InvoiceItem, ProcessingBatch, ProcessingYield  # noqa

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # --- Brand colors (Rizara) ---
    JUNGLE = colors.HexColor("#1f6f54")
    GOLD = colors.HexColor("#d4af37")
    GRAY = colors.HexColor("#6b7280")
    DARK = colors.HexColor("#111827")

    # --- Header bar ---
    c.setFillColor(JUNGLE)
    c.rect(0, height - 28 * mm, width, 28 * mm, stroke=0, fill=1)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(18 * mm, height - 16 * mm, "Rizara Meats Ltd")

    c.setFont("Helvetica", 9)
    c.drawString(18 * mm, height - 22 * mm, "Secure • Traceable • Halal")

    # --- Invoice meta (top right) ---
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    inv_no = getattr(invoice, "invoice_number", None) or f"INV-{getattr(invoice, 'id', '')}"
    c.drawRightString(width - 18 * mm, height - 14 * mm, f"INVOICE {inv_no}")

    c.setFont("Helvetica", 9)
    status = _safe_enum_value(getattr(invoice, "status", "issued"))
    issue_date = _fmt_date(getattr(invoice, "issue_date", None))
    c.drawRightString(width - 18 * mm, height - 20 * mm, f"Status: {status} • Issue: {issue_date}")

    # --- Body start ---
    y = height - 38 * mm

    # Buyer info card
    buyer = getattr(invoice, "buyer", None)
    buyer_name = getattr(buyer, "name", "-") if buyer else "-"
    buyer_phone = getattr(buyer, "phone", "") if buyer else ""
    buyer_email = getattr(buyer, "email", "") if buyer else ""
    buyer_addr = getattr(buyer, "address", "") if buyer else ""

    # Related batch/yield (best effort)
    sale = getattr(invoice, "sale", None)
    batch = None
    yrec = None
    currency = "KES"

    try:
        if sale:
            currency = getattr(sale, "currency", None) or currency
            pb_id = getattr(sale, "processing_batch_id", None)
            if pb_id:
                batch = ProcessingBatch.query.get(pb_id)
                if batch:
                    yrec = ProcessingYield.query.filter_by(processing_batch_id=batch.id).first()
    except Exception:
        # If DB unavailable, just skip batch/yield details.
        batch = None
        yrec = None

    # Draw section headings
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(18 * mm, y, "Billed To")
    c.drawString(width / 2 + 2 * mm, y, "Batch Details")
    y -= 6 * mm

    # Left: buyer box
    c.setStrokeColor(colors.HexColor("#e5e7eb"))
    c.setFillColor(colors.white)
    c.roundRect(18 * mm, y - 30 * mm, (width / 2 - 22 * mm), 30 * mm, 6, stroke=1, fill=1)

    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(22 * mm, y - 8 * mm, buyer_name)

    c.setFont("Helvetica", 9)
    line_y = y - 14 * mm
    if buyer_phone:
        c.drawString(22 * mm, line_y, buyer_phone)
        line_y -= 5 * mm
    if buyer_email:
        c.drawString(22 * mm, line_y, buyer_email)
        line_y -= 5 * mm
    if buyer_addr:
        c.setFillColor(GRAY)
        c.drawString(22 * mm, line_y, buyer_addr[:75])
        c.setFillColor(DARK)

    # Right: batch box
    right_x = width / 2 + 2 * mm
    c.setStrokeColor(colors.HexColor("#e5e7eb"))
    c.setFillColor(colors.white)
    c.roundRect(right_x, y - 30 * mm, (width - right_x - 18 * mm), 30 * mm, 6, stroke=1, fill=1)

    c.setFillColor(DARK)
    c.setFont("Helvetica", 9)

    if batch:
        c.drawString(right_x + 4 * mm, y - 10 * mm, f"Processing Batch: #{batch.id}")
        c.drawString(right_x + 4 * mm, y - 15 * mm, f"Animal Type: {getattr(batch, 'animal_type', '-')}")
        c.drawString(right_x + 4 * mm, y - 20 * mm, f"Facility: {getattr(batch, 'facility', '-')}")
        c.drawString(right_x + 4 * mm, y - 25 * mm, f"Slaughter Date: {_fmt_date(getattr(batch, 'slaughter_date', None))}")
        if yrec:
            c.setFillColor(GRAY)
            cw = getattr(yrec, "total_carcass_weight_kg", None)
            c.drawString(right_x + 4 * mm, y - 30 * mm + 5 * mm, f"Carcass: {cw} kg" if cw is not None else "Carcass: -")
            c.setFillColor(DARK)
    else:
        c.drawString(right_x + 4 * mm, y - 12 * mm, "Batch details not available")

    y -= 40 * mm

    # --- Items table ---
    items = []
    try:
        items = InvoiceItem.query.filter_by(invoice_id=invoice.id).all()
    except Exception:
        items = []

    data = [["Description", "Qty", "Unit Price", "Line Total"]]
    for it in items:
        data.append([
            getattr(it, "description", "-"),
            f"{getattr(it, 'quantity', 1.0)}",
            _money(getattr(it, "unit_price", 0.0), currency),
            _money(getattr(it, "line_total", 0.0), currency),
        ])

    if len(data) == 1:
        data.append(["(No items found)", "-", "-", "-"])

    table = Table(
        data,
        colWidths=[98 * mm, 18 * mm, 30 * mm, 30 * mm],
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
        ("TEXTCOLOR", (0, 0), (-1, 0), DARK),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))

    tw, th = table.wrapOn(c, width - 36 * mm, height)
    table.drawOn(c, 18 * mm, y - th)

    y = y - th - 10 * mm

    # --- Totals ---
    subtotal = getattr(invoice, "subtotal", 0.0) or 0.0
    tax = getattr(invoice, "tax", 0.0) or 0.0
    total = getattr(invoice, "total", 0.0) or 0.0

    # Right aligned totals block
    block_x = width - 18 * mm
    c.setFont("Helvetica", 9)
    c.setFillColor(GRAY)
    c.drawRightString(block_x, y, "Subtotal")
    c.drawRightString(block_x, y - 6 * mm, "Tax")
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(block_x, y - 14 * mm, "Total")

    c.setFont("Helvetica", 9)
    c.setFillColor(DARK)
    c.drawRightString(block_x - 40 * mm, y, _money(subtotal, currency))
    c.drawRightString(block_x - 40 * mm, y - 6 * mm, _money(tax, currency))
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(block_x - 40 * mm, y - 14 * mm, _money(total, currency))

    y -= 24 * mm

    # --- Notes / Terms ---
    notes = getattr(invoice, "notes", None)
    terms = getattr(invoice, "terms", None) or "Payment due as agreed."

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(DARK)
    c.drawString(18 * mm, y, "Terms")
    c.setFont("Helvetica", 9)
    c.setFillColor(GRAY)
    c.drawString(18 * mm, y - 6 * mm, (terms or "")[:120])

    if notes:
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(DARK)
        c.drawString(18 * mm, y - 16 * mm, "Notes")
        c.setFont("Helvetica", 9)
        c.setFillColor(GRAY)
        c.drawString(18 * mm, y - 22 * mm, (notes or "")[:120])

    # --- Footer ---
    c.setFillColor(colors.HexColor("#e5e7eb"))
    c.rect(0, 0, width, 12 * mm, stroke=0, fill=1)

    c.setFillColor(colors.HexColor("#374151"))
    c.setFont("Helvetica", 8)
    c.drawString(18 * mm, 4 * mm, "Rizara Meats Ltd • Nairobi, Kenya • For support contact Rizara Admin")
    c.setFillColor(colors.HexColor("#6b7280"))
    c.drawRightString(width - 18 * mm, 4 * mm, f"Generated: {_fmt_date(date.today())}")

    c.showPage()
    c.save()

    pdf = buf.getvalue()
    buf.close()
    return pdf
