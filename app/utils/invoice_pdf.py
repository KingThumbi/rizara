# app/utils/invoice_pdf.py
from __future__ import annotations

import io
from datetime import date, datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle


def _fmt_date(value):
    if not value:
        return "-"
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _money(value, currency="USD"):
    return f"{currency} {_decimal(value):,.2f}"


def _safe_enum_value(value):
    try:
        return value.value
    except Exception:
        return str(value) if value is not None else "-"


def _paragraph(text, style):
    return Paragraph(str(text or "-").replace("&", "&amp;"), style)


def render_invoice_pdf(invoice) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    JUNGLE = colors.HexColor("#1f6f54")
    GRAY = colors.HexColor("#6b7280")
    DARK = colors.HexColor("#111827")
    LIGHT = colors.HexColor("#f9fafb")
    BORDER = colors.HexColor("#e5e7eb")

    styles = getSampleStyleSheet()

    ref_label_style = ParagraphStyle(
        "RefLabel",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=GRAY,
        alignment=TA_LEFT,
    )

    ref_value_style = ParagraphStyle(
        "RefValue",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=DARK,
        alignment=TA_LEFT,
    )

    buyer = getattr(invoice, "buyer", None)
    contract = getattr(invoice, "contract", None)
    contract_document = getattr(invoice, "contract_document", None)
    batch = getattr(invoice, "commercial_processing_batch", None)

    currency = getattr(invoice, "currency", None) or "USD"

    subtotal = _decimal(getattr(invoice, "subtotal", 0))
    tax = _decimal(getattr(invoice, "tax", 0))
    total = _decimal(getattr(invoice, "total", 0))
    deposit_paid = _decimal(getattr(invoice, "deposit_paid", 0))
    balance_due = _decimal(getattr(invoice, "balance", total - deposit_paid))

    # Header
    c.setFillColor(JUNGLE)
    c.rect(0, height - 30 * mm, width, 30 * mm, stroke=0, fill=1)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(18 * mm, height - 15 * mm, "Rizara Meats Ltd")

    c.setFont("Helvetica", 9)
    c.drawString(18 * mm, height - 22 * mm, "Ethical • Traceable • Halal")

    invoice_number = getattr(invoice, "invoice_number", None) or f"INV-{getattr(invoice, 'id', '')}"
    status = _safe_enum_value(getattr(invoice, "status", "issued"))
    issue_date = _fmt_date(getattr(invoice, "issue_date", None))

    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(width - 18 * mm, height - 14 * mm, "COMMERCIAL INVOICE")
    c.setFont("Helvetica", 9)
    c.drawRightString(width - 18 * mm, height - 20 * mm, f"No: {invoice_number}")
    c.drawRightString(width - 18 * mm, height - 25 * mm, f"Status: {status} | Issue: {issue_date}")

    y = height - 42 * mm

    # Buyer and commercial references headings
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(18 * mm, y, "Billed To")
    c.drawString(width / 2 + 2 * mm, y, "Commercial References")
    y -= 6 * mm

    left_x = 18 * mm
    right_x = width / 2 + 2 * mm
    box_h = 46 * mm

    # Buyer box
    c.setStrokeColor(BORDER)
    c.setFillColor(colors.white)
    c.roundRect(left_x, y - box_h, width / 2 - 24 * mm, box_h, 6, stroke=1, fill=1)

    buyer_name = getattr(buyer, "name", "-") if buyer else "-"
    buyer_phone = getattr(buyer, "phone", "") if buyer else ""
    buyer_email = getattr(buyer, "email", "") if buyer else ""
    buyer_addr = getattr(buyer, "address", "") if buyer else ""

    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left_x + 4 * mm, y - 8 * mm, str(buyer_name)[:45])

    c.setFont("Helvetica", 9)
    line_y = y - 14 * mm
    for text in [buyer_phone, buyer_email, buyer_addr]:
        if text:
            c.drawString(left_x + 4 * mm, line_y, str(text)[:55])
            line_y -= 5 * mm

    # Commercial references box
    c.setStrokeColor(BORDER)
    c.setFillColor(colors.white)
    ref_box_w = width - right_x - 18 * mm
    c.roundRect(right_x, y - box_h, ref_box_w, box_h, 6, stroke=1, fill=1)

    contract_ref = getattr(contract, "contract_number", "-") if contract else "-"

    if contract_document:
        document_ref = (
            getattr(contract_document, "title", None)
            or getattr(contract_document, "original_filename", None)
            or getattr(contract_document, "stored_filename", None)
            or f"DOC-{contract_document.id}"
        )
    else:
        document_ref = "-"

    batch_ref = getattr(batch, "batch_number", "-") if batch else "-"

    refs = [
        ("Contract", contract_ref),
        ("Document", document_ref),
        ("Batch", batch_ref),
        ("Currency", currency),
    ]

    ref_data = [
        [
            _paragraph(f"{label}:", ref_label_style),
            _paragraph(value, ref_value_style),
        ]
        for label, value in refs
    ]

    ref_table = Table(
        ref_data,
        colWidths=[23 * mm, ref_box_w - 31 * mm],
        hAlign="LEFT",
    )

    ref_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    _, ref_table_h = ref_table.wrapOn(c, ref_box_w - 8 * mm, box_h - 8 * mm)
    ref_table.drawOn(c, right_x + 4 * mm, y - 6 * mm - ref_table_h)

    y -= box_h + 12 * mm

    # Items
    data = [["Description", "Qty", "Unit Price", "Line Total"]]

    for item in getattr(invoice, "items", []):
        data.append([
            str(getattr(item, "description", "-"))[:65],
            f"{_decimal(getattr(item, 'quantity', 0)):,.2f}",
            _money(getattr(item, "unit_price", 0), currency),
            _money(getattr(item, "line_total", 0), currency),
        ])

    if len(data) == 1:
        data.append(["No invoice items found", "-", "-", "-"])

    table = Table(
        data,
        colWidths=[90 * mm, 22 * mm, 34 * mm, 34 * mm],
        hAlign="LEFT",
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
        ("TEXTCOLOR", (0, 0), (-1, 0), DARK),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))

    _, table_height = table.wrapOn(c, width - 36 * mm, height)
    table.drawOn(c, 18 * mm, y - table_height)
    y = y - table_height - 10 * mm

    # Totals
    box_w = 82 * mm
    box_x = width - 18 * mm - box_w
    box_y = y - 48 * mm

    c.setFillColor(LIGHT)
    c.setStrokeColor(BORDER)
    c.roundRect(box_x, box_y, box_w, 48 * mm, 6, stroke=1, fill=1)

    label_x = box_x + 5 * mm
    value_x = box_x + box_w - 5 * mm
    row_y = y - 8 * mm

    totals = [
        ("Subtotal", subtotal, False),
        ("Tax", tax, False),
        ("Total Invoice Value", total, True),
        ("Deposit / Payments Received", deposit_paid, False),
        ("Balance Due", balance_due, True),
    ]

    for label, value, bold in totals:
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 9)
        c.setFillColor(JUNGLE if label == "Balance Due" else DARK)
        c.drawString(label_x, row_y, label)
        c.drawRightString(value_x, row_y, _money(value, currency))
        row_y -= 8 * mm

    y = box_y - 12 * mm

    # Terms / Notes
    terms = getattr(invoice, "terms", None) or "Payment as agreed."
    notes = getattr(invoice, "notes", None)

    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(18 * mm, y, "Terms")

    c.setFillColor(GRAY)
    c.setFont("Helvetica", 9)
    c.drawString(18 * mm, y - 6 * mm, str(terms)[:120])

    if notes:
        c.setFillColor(DARK)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(18 * mm, y - 17 * mm, "Notes")
        c.setFillColor(GRAY)
        c.setFont("Helvetica", 9)
        c.drawString(18 * mm, y - 23 * mm, str(notes)[:120])

    # Footer
    c.setFillColor(colors.HexColor("#e5e7eb"))
    c.rect(0, 0, width, 12 * mm, stroke=0, fill=1)

    c.setFillColor(colors.HexColor("#374151"))
    c.setFont("Helvetica", 8)
    c.drawString(18 * mm, 4 * mm, "Rizara Meats Ltd • Nairobi, Kenya")

    c.setFillColor(colors.HexColor("#6b7280"))
    c.drawRightString(width - 18 * mm, 4 * mm, f"Generated: {_fmt_date(date.today())}")

    c.showPage()
    c.save()

    pdf = buf.getvalue()
    buf.close()
    return pdf