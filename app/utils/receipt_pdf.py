# app/utils/receipt_pdf.py
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


def _fmt_date(value, with_time: bool = False):
    if not value:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M") if with_time else value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _money(value, currency="USD") -> str:
    return f"{currency} {_decimal(value):,.2f}"


def _safe_enum_value(value):
    try:
        return value.value
    except Exception:
        return str(value) if value is not None else "-"


def _paragraph(text, style):
    safe = str(text or "-").replace("&", "&amp;")
    return Paragraph(safe, style)


def _receipt_number(payment) -> str:
    if getattr(payment, "receipt_number", None):
        return payment.receipt_number

    paid_at = getattr(payment, "paid_at", None)
    year = paid_at.year if paid_at else date.today().year
    return f"RCT-{year}-{payment.id:05d}"


def render_payment_receipt_pdf(invoice, payment) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    JUNGLE = colors.HexColor("#1f6f54")
    GOLD = colors.HexColor("#d4af37")
    GRAY = colors.HexColor("#6b7280")
    DARK = colors.HexColor("#111827")
    LIGHT = colors.HexColor("#f9fafb")
    BORDER = colors.HexColor("#e5e7eb")
    GREEN_SOFT = colors.HexColor("#ecfdf5")
    GREEN_BORDER = colors.HexColor("#bbf7d0")

    styles = getSampleStyleSheet()

    small_gray = ParagraphStyle(
        "SmallGray",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=GRAY,
        alignment=TA_LEFT,
    )

    small_dark = ParagraphStyle(
        "SmallDark",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=DARK,
        alignment=TA_LEFT,
    )

    confirm_style = ParagraphStyle(
        "ConfirmText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=10.5,
        textColor=GRAY,
        alignment=TA_LEFT,
    )

    currency = getattr(invoice, "currency", None) or "USD"
    buyer = getattr(invoice, "buyer", None)
    contract_doc = getattr(invoice, "contract_document", None)
    contract = getattr(invoice, "contract", None) or (
        contract_doc.contract if contract_doc and getattr(contract_doc, "contract", None) else None
    )

    receipt_no = _receipt_number(payment)
    invoice_no = getattr(invoice, "invoice_number", "-")
    invoice_status = _safe_enum_value(getattr(invoice, "status", "-"))

    amount = _decimal(getattr(payment, "amount", 0))
    invoice_total = _decimal(getattr(invoice, "total", 0))
    total_paid = _decimal(getattr(invoice, "deposit_paid", 0))
    balance = _decimal(getattr(invoice, "balance", 0))

    # Header
    c.setFillColor(JUNGLE)
    c.rect(0, height - 32 * mm, width, 32 * mm, stroke=0, fill=1)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(18 * mm, height - 15 * mm, "Rizara Meats Ltd")

    c.setFont("Helvetica", 9)
    c.drawString(18 * mm, height - 22 * mm, "Ethical • Traceable • Halal")

    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(width - 18 * mm, height - 14 * mm, "PAYMENT RECEIPT")

    c.setFont("Helvetica", 9)
    c.drawRightString(width - 18 * mm, height - 20 * mm, f"No: {receipt_no}")
    c.drawRightString(
        width - 18 * mm,
        height - 25 * mm,
        f"Invoice: {invoice_no} | Date: {_fmt_date(getattr(payment, 'paid_at', None), with_time=True)}",
    )

    y = height - 44 * mm

    # Payment highlight
    c.setFillColor(GREEN_SOFT)
    c.setStrokeColor(GREEN_BORDER)
    c.roundRect(18 * mm, y - 25 * mm, width - 36 * mm, 25 * mm, 8, stroke=1, fill=1)

    c.setFillColor(JUNGLE)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(24 * mm, y - 9 * mm, "PAYMENT RECEIVED")

    c.setFont("Helvetica-Bold", 22)
    c.drawString(24 * mm, y - 19 * mm, _money(amount, currency))

    c.setFillColor(DARK)
    c.setFont("Helvetica", 9)
    c.drawRightString(width - 24 * mm, y - 10 * mm, f"Receipt Number: {receipt_no}")
    c.drawRightString(width - 24 * mm, y - 17 * mm, "Status: Confirmed")

    y -= 38 * mm

    # Buyer + payment details
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(18 * mm, y, "Received From")
    c.drawString(width / 2 + 2 * mm, y, "Payment Details")
    y -= 6 * mm

    left_x = 18 * mm
    right_x = width / 2 + 2 * mm
    box_h = 42 * mm
    left_w = width / 2 - 24 * mm
    right_w = width - right_x - 18 * mm

    c.setFillColor(colors.white)
    c.setStrokeColor(BORDER)
    c.roundRect(left_x, y - box_h, left_w, box_h, 6, stroke=1, fill=1)
    c.roundRect(right_x, y - box_h, right_w, box_h, 6, stroke=1, fill=1)

    buyer_name = getattr(buyer, "name", "-") if buyer else "-"
    buyer_email = getattr(buyer, "email", "") if buyer else ""
    buyer_phone = getattr(buyer, "phone", "") if buyer else ""
    buyer_address = getattr(buyer, "address", "") if buyer else ""

    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left_x + 4 * mm, y - 8 * mm, str(buyer_name)[:44])

    c.setFont("Helvetica", 9)
    line_y = y - 14 * mm
    for text in [buyer_phone, buyer_email, buyer_address]:
        if text:
            c.drawString(left_x + 4 * mm, line_y, str(text)[:55])
            line_y -= 5 * mm

    detail_rows = [
        ("Method", (getattr(payment, "method", None) or "-").replace("_", " ").title()),
        ("Reference", getattr(payment, "reference", None) or "-"),
        ("Payment Date", _fmt_date(getattr(payment, "paid_at", None), with_time=True)),
        ("Invoice Status", str(invoice_status).replace("_", " ").title()),
        ("Notes", getattr(payment, "notes", None) or "-"),
    ]

    detail_data = [
        [_paragraph(f"{label}:", small_gray), _paragraph(value, small_dark)]
        for label, value in detail_rows
    ]

    detail_table = Table(detail_data, colWidths=[25 * mm, right_w - 33 * mm], hAlign="LEFT")
    detail_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    _, detail_h = detail_table.wrapOn(c, right_w - 8 * mm, box_h - 8 * mm)
    detail_table.drawOn(c, right_x + 4 * mm, y - 6 * mm - detail_h)

    y -= box_h + 13 * mm

    # Commercial reference
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(18 * mm, y, "Commercial Reference")
    y -= 6 * mm

    ref_box_h = 30 * mm
    c.setFillColor(colors.white)
    c.setStrokeColor(BORDER)
    c.roundRect(18 * mm, y - ref_box_h, width - 36 * mm, ref_box_h, 6, stroke=1, fill=1)

    contract_ref = getattr(contract, "contract_number", "-") if contract else "-"

    doc_ref = "-"
    if contract_doc:
        doc_ref = (
            getattr(contract_doc, "title", None)
            or getattr(contract_doc, "original_filename", None)
            or getattr(contract_doc, "stored_filename", None)
            or f"DOC-{contract_doc.id}"
        )

    ref_data = [
        [_paragraph("Invoice:", small_gray), _paragraph(invoice_no, small_dark)],
        [_paragraph("Contract:", small_gray), _paragraph(contract_ref, small_dark)],
        [_paragraph("Document:", small_gray), _paragraph(doc_ref, small_dark)],
    ]

    ref_table = Table(ref_data, colWidths=[25 * mm, width - 69 * mm], hAlign="LEFT")
    ref_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    _, ref_h = ref_table.wrapOn(c, width - 44 * mm, ref_box_h - 8 * mm)
    ref_table.drawOn(c, 22 * mm, y - 6 * mm - ref_h)

    y -= ref_box_h + 12 * mm

    # Financial summary
    box_w = 90 * mm
    box_x = width - 18 * mm - box_w
    box_y = y - 48 * mm

    c.setFillColor(LIGHT)
    c.setStrokeColor(BORDER)
    c.roundRect(box_x, box_y, box_w, 48 * mm, 6, stroke=1, fill=1)

    label_x = box_x + 5 * mm
    value_x = box_x + box_w - 5 * mm
    row_y = y - 8 * mm

    totals = [
        ("Invoice Total", invoice_total, True),
        ("This Payment", amount, True),
        ("Total Paid To Date", total_paid, False),
        ("Remaining Balance", balance, True),
    ]

    for label, value, bold in totals:
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 9)
        c.setFillColor(JUNGLE if label in {"This Payment", "Remaining Balance"} else DARK)
        c.drawString(label_x, row_y, label)
        c.drawRightString(value_x, row_y, _money(value, currency))
        row_y -= 9 * mm

    # Wrapped confirmation note
    note_x = 18 * mm
    note_y = y - 8 * mm
    note_w = box_x - note_x - 10 * mm

    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(note_x, note_y, "Receipt Confirmation")

    confirmation_text = (
        "Payment received and recorded against this invoice. "
        "Please retain this receipt for your records and reconciliation."
    )

    confirm_para = Paragraph(confirmation_text, confirm_style)
    _, confirm_h = confirm_para.wrap(note_w, 24 * mm)
    confirm_para.drawOn(c, note_x, note_y - 6 * mm - confirm_h)

    y = box_y - 14 * mm

    # Footer
    c.setFillColor(colors.HexColor("#e5e7eb"))
    c.rect(0, 0, width, 14 * mm, stroke=0, fill=1)

    c.setFillColor(colors.HexColor("#374151"))
    c.setFont("Helvetica", 8)
    c.drawString(18 * mm, 5 * mm, "Rizara Meats Ltd • Nairobi, Kenya • sales@rizarameats.co.ke")

    c.setFillColor(colors.HexColor("#6b7280"))
    c.drawRightString(width - 18 * mm, 5 * mm, f"Generated: {_fmt_date(date.today())}")

    c.showPage()
    c.save()

    pdf = buf.getvalue()
    buf.close()
    return pdf