# /home/thumbi/rizara/app/utils/receipt_pdf.py

from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Table, TableStyle

from .pdf_theme import (
    NumberedCanvas,
    draw_footer,
    draw_header,
    fmt_date,
    decimalize,
    money,
    status_label,
    safe_text,
    p,
    make_styles,
    JUNGLE,
    GOLD,
    DARK,
    GRAY,
    LIGHT,
    BORDER,
    GREEN_SOFT,
    GREEN_BORDER,
    GOLD_SOFT,
    TEXT_FONT,
    TEXT_BOLD,
    NUM_FONT,
    NUM_BOLD,
)


def _receipt_number(payment) -> str:
    if getattr(payment, "receipt_number", None):
        return str(payment.receipt_number)

    paid_at = getattr(payment, "paid_at", None)
    year = paid_at.year if paid_at else date.today().year

    return f"RCT-{year}-{getattr(payment, 'id', 0):05d}"


def _contract_document_ref(contract_document) -> str:
    if not contract_document:
        return "-"

    return (
        getattr(contract_document, "title", None)
        or getattr(contract_document, "original_filename", None)
        or getattr(contract_document, "stored_filename", None)
        or f"DOC-{getattr(contract_document, 'id', '-')}"
    )


def _contract_ref(contract) -> str:
    if not contract:
        return "-"

    return (
        getattr(contract, "contract_number", None)
        or getattr(contract, "reference", None)
        or f"CONTRACT-{getattr(contract, 'id', '-')}"
    )


def _payment_method(payment) -> str:
    method = getattr(payment, "method", None) or "-"
    return str(method).replace("_", " ").title()


def render_payment_receipt_pdf(invoice, payment) -> bytes:
    buffer = io.BytesIO()
    c = NumberedCanvas(buffer, pagesize=A4, footer_func=draw_footer)

    width, height = A4
    today = date.today()

    styles = make_styles()
    sample_styles = getSampleStyleSheet()

    label_style = ParagraphStyle(
        "ReceiptLabel",
        parent=sample_styles["Normal"],
        fontName=TEXT_FONT,
        fontSize=8,
        leading=10,
        textColor=GRAY,
        alignment=TA_LEFT,
    )

    value_style = ParagraphStyle(
        "ReceiptValue",
        parent=sample_styles["Normal"],
        fontName=TEXT_FONT,
        fontSize=8,
        leading=10,
        textColor=DARK,
        alignment=TA_LEFT,
    )

    note_style = ParagraphStyle(
        "ReceiptNote",
        parent=sample_styles["Normal"],
        fontName=TEXT_FONT,
        fontSize=8.5,
        leading=10.5,
        textColor=GRAY,
        alignment=TA_LEFT,
    )

    currency = getattr(invoice, "currency", None) or "USD"
    buyer = getattr(invoice, "buyer", None)

    contract_document = getattr(invoice, "contract_document", None)
    contract = getattr(invoice, "contract", None) or (
        contract_document.contract
        if contract_document and getattr(contract_document, "contract", None)
        else None
    )

    receipt_no = _receipt_number(payment)
    invoice_no = getattr(invoice, "invoice_number", "-")
    invoice_status = status_label(getattr(invoice, "status", "-"))

    amount = decimalize(getattr(payment, "amount", 0))
    invoice_total = decimalize(getattr(invoice, "total", 0))
    total_paid = decimalize(getattr(invoice, "deposit_paid", 0))
    balance = decimalize(getattr(invoice, "balance", 0))

    paid_at = getattr(payment, "paid_at", None)

    draw_header(
        c,
        title="PAYMENT RECEIPT",
        right_line_1=f"No: {receipt_no}",
        right_line_2=f"Invoice: {invoice_no} | Date: {fmt_date(paid_at, with_time=True)}",
    )

    y = height - 44 * mm

    # Payment received hero
    c.setFillColor(GREEN_SOFT)
    c.setStrokeColor(GREEN_BORDER)
    c.roundRect(18 * mm, y - 28 * mm, width - 36 * mm, 28 * mm, 8, stroke=1, fill=1)

    c.setFillColor(JUNGLE)
    c.setFont(TEXT_BOLD, 10)
    c.drawString(24 * mm, y - 9 * mm, "PAYMENT RECEIVED")

    c.setFont(NUM_BOLD, 21)
    c.drawString(24 * mm, y - 20 * mm, money(amount, currency))

    c.setFillColor(DARK)
    c.setFont(TEXT_FONT, 9)
    c.drawRightString(width - 24 * mm, y - 10 * mm, f"Receipt Number: {receipt_no}")
    c.drawRightString(width - 24 * mm, y - 17 * mm, "Status: Confirmed")

    y -= 40 * mm

    # Received from + payment details
    c.setFillColor(DARK)
    c.setFont(TEXT_BOLD, 11)
    c.drawString(18 * mm, y, "Received From")
    c.drawString(width / 2 + 2 * mm, y, "Payment Details")
    y -= 6 * mm

    left_x = 18 * mm
    right_x = width / 2 + 2 * mm
    box_h = 45 * mm
    left_w = width / 2 - 24 * mm
    right_w = width - right_x - 18 * mm

    c.setFillColor(colors.white)
    c.setStrokeColor(BORDER)
    c.roundRect(left_x, y - box_h, left_w, box_h, 6, stroke=1, fill=1)
    c.roundRect(right_x, y - box_h, right_w, box_h, 6, stroke=1, fill=1)

    buyer_name = getattr(buyer, "name", "-") if buyer else "-"
    buyer_phone = getattr(buyer, "phone", "") if buyer else ""
    buyer_email = getattr(buyer, "email", "") if buyer else ""
    buyer_address = getattr(buyer, "address", "") if buyer else ""

    c.setFillColor(DARK)
    c.setFont(TEXT_BOLD, 10)
    c.drawString(left_x + 4 * mm, y - 8 * mm, str(buyer_name)[:44])

    c.setFont(TEXT_FONT, 9)
    buyer_y = y - 15 * mm
    for text in [buyer_phone, buyer_email, buyer_address]:
        if text:
            c.drawString(left_x + 4 * mm, buyer_y, str(text)[:55])
            buyer_y -= 6 * mm

    detail_rows = [
        ("Method", _payment_method(payment)),
        ("Reference", getattr(payment, "reference", None) or "-"),
        ("Payment Date", fmt_date(paid_at, with_time=True)),
        ("Invoice Status", invoice_status),
        ("Notes", getattr(payment, "notes", None) or "-"),
    ]

    detail_data = [
        [p(f"{label}:", label_style), p(value, value_style)]
        for label, value in detail_rows
    ]

    detail_table = Table(
        detail_data,
        colWidths=[26 * mm, right_w - 34 * mm],
        hAlign="LEFT",
    )

    detail_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    _, detail_h = detail_table.wrapOn(c, right_w - 8 * mm, box_h - 8 * mm)
    detail_table.drawOn(c, right_x + 4 * mm, y - 6 * mm - detail_h)

    y -= box_h + 14 * mm

    # Commercial reference
    c.setFillColor(DARK)
    c.setFont(TEXT_BOLD, 11)
    c.drawString(18 * mm, y, "Commercial Reference")
    y -= 6 * mm

    ref_box_h = 34 * mm

    c.setFillColor(colors.white)
    c.setStrokeColor(BORDER)
    c.roundRect(18 * mm, y - ref_box_h, width - 36 * mm, ref_box_h, 6, stroke=1, fill=1)

    ref_rows = [
        ("Invoice", invoice_no),
        ("Contract", _contract_ref(contract)),
        ("Document", _contract_document_ref(contract_document)),
        ("Currency", currency),
    ]

    ref_data = [
        [p(f"{label}:", label_style), p(value, value_style)]
        for label, value in ref_rows
    ]

    ref_table = Table(
        ref_data,
        colWidths=[25 * mm, width - 69 * mm],
        hAlign="LEFT",
    )

    ref_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    _, ref_h = ref_table.wrapOn(c, width - 44 * mm, ref_box_h - 8 * mm)
    ref_table.drawOn(c, 22 * mm, y - 6 * mm - ref_h)

    y -= ref_box_h + 14 * mm

    # Financial summary + confirmation
    box_w = 92 * mm
    box_x = width - 18 * mm - box_w
    box_h = 50 * mm
    box_y = y - box_h

    note_x = 18 * mm
    note_w = box_x - note_x - 10 * mm

    c.setFillColor(colors.white)
    c.setStrokeColor(BORDER)
    c.roundRect(note_x, box_y, note_w, box_h, 6, stroke=1, fill=1)

    c.setFillColor(DARK)
    c.setFont(TEXT_BOLD, 10)
    c.drawString(note_x + 4 * mm, y - 8 * mm, "Receipt Confirmation")

    confirmation_text = (
        "Payment received and recorded against this invoice. "
        "Please retain this receipt for your records, reconciliation, and settlement follow-up."
    )

    confirm_para = Paragraph(safe_text(confirmation_text), note_style)
    _, confirm_h = confirm_para.wrap(note_w - 8 * mm, box_h - 16 * mm)
    confirm_para.drawOn(c, note_x + 4 * mm, y - 15 * mm - confirm_h)

    c.setFillColor(LIGHT)
    c.setStrokeColor(BORDER)
    c.roundRect(box_x, box_y, box_w, box_h, 6, stroke=1, fill=1)

    totals = [
        ("Invoice Total", invoice_total, True),
        ("This Payment", amount, True),
        ("Total Paid To Date", total_paid, False),
        ("Remaining Balance", balance, True),
    ]

    row_y = y - 9 * mm
    label_x = box_x + 5 * mm
    value_x = box_x + box_w - 5 * mm

    for label, value, bold in totals:
        c.setFillColor(JUNGLE if label in {"This Payment", "Remaining Balance"} else DARK)
        c.setFont(TEXT_BOLD if bold else TEXT_FONT, 9)
        c.drawString(label_x, row_y, label)

        c.setFont(NUM_BOLD if bold else NUM_FONT, 9)
        c.drawRightString(value_x, row_y, money(value, currency))

        row_y -= 10 * mm

    y = box_y - 14 * mm

    # Compact audit trail
    audit_h = 28 * mm

    if y - audit_h < 24 * mm:
        c.showPage()
        y = height - 24 * mm

    c.setFillColor(colors.white)
    c.setStrokeColor(BORDER)
    c.roundRect(18 * mm, y - audit_h, width - 36 * mm, audit_h, 6, stroke=1, fill=1)

    c.setFillColor(DARK)
    c.setFont(TEXT_BOLD, 10)
    c.drawString(22 * mm, y - 8 * mm, "Audit Trail")

    audit_data = [[
        p("Receipt No.", styles["small_gray"]),
        p("Invoice No.", styles["small_gray"]),
        p("Payment Ref.", styles["small_gray"]),
        p("As At", styles["small_gray"]),
    ], [
        p(receipt_no, styles["small_dark"]),
        p(invoice_no, styles["small_dark"]),
        p(getattr(payment, "reference", None) or "-", styles["small_dark"]),
        p(fmt_date(today), styles["small_dark"]),
    ]]

    audit_table = Table(
        audit_data,
        colWidths=[42 * mm, 42 * mm, 58 * mm, 34 * mm],
        hAlign="LEFT",
    )

    audit_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
        ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    _, audit_table_h = audit_table.wrapOn(c, width - 44 * mm, audit_h - 10 * mm)
    audit_table.drawOn(c, 22 * mm, y - 12 * mm - audit_table_h)

    c.showPage()
    c.save()

    pdf = buffer.getvalue()
    buffer.close()

    return pdf