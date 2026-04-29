# /home/thumbi/rizara/app/utils/invoice_pdf.py

from __future__ import annotations

import io
from datetime import date, datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
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


def _invoice_number(invoice) -> str:
    return getattr(invoice, "invoice_number", None) or f"INV-{getattr(invoice, 'id', '')}"


def _invoice_date(invoice):
    return (
        getattr(invoice, "issue_date", None)
        or getattr(invoice, "invoice_date", None)
        or getattr(invoice, "issued_at", None)
        or getattr(invoice, "created_at", None)
    )


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
    return getattr(contract, "contract_number", None) or f"CONTRACT-{getattr(contract, 'id', '-')}"


def _batch_ref(batch) -> str:
    if not batch:
        return "-"
    return (
        getattr(batch, "batch_number", None)
        or getattr(batch, "reference", None)
        or getattr(batch, "code", None)
        or f"BATCH-{getattr(batch, 'id', '-')}"
    )


def _terms_from_invoice_or_contract(invoice, contract) -> str:
    invoice_terms = getattr(invoice, "terms", None)
    if invoice_terms:
        return str(invoice_terms)

    if contract:
        payment_security = getattr(contract, "payment_security_type", None)
        release_mode = getattr(contract, "processing_release_mode", None)

        pieces = []

        if payment_security:
            pieces.append(f"Payment security: {str(payment_security).replace('_', ' ').title()}.")

        if release_mode:
            pieces.append(f"Processing release: {str(release_mode).replace('_', ' ').title()}.")

        if pieces:
            return " ".join(pieces)

    return "Payment as agreed between Rizara Meats Ltd and the buyer."


def _draw_section_title(c, title: str, x: float, y: float):
    c.setFillColor(DARK)
    c.setFont(TEXT_BOLD, 11)
    c.drawString(x, y, title)


def render_invoice_pdf(invoice) -> bytes:
    buffer = io.BytesIO()
    c = NumberedCanvas(buffer, pagesize=A4, footer_func=draw_footer)

    width, height = A4
    today = date.today()
    styles = make_styles()
    sample_styles = getSampleStyleSheet()

    note_style = ParagraphStyle(
        "InvoiceNote",
        parent=sample_styles["Normal"],
        fontName=TEXT_FONT,
        fontSize=8.5,
        leading=10.5,
        textColor=GRAY,
        alignment=TA_LEFT,
    )

    label_style = ParagraphStyle(
        "InvoiceLabel",
        parent=sample_styles["Normal"],
        fontName=TEXT_FONT,
        fontSize=8,
        leading=10,
        textColor=GRAY,
        alignment=TA_LEFT,
    )

    value_style = ParagraphStyle(
        "InvoiceValue",
        parent=sample_styles["Normal"],
        fontName=TEXT_FONT,
        fontSize=8,
        leading=10,
        textColor=DARK,
        alignment=TA_LEFT,
    )

    value_right_style = ParagraphStyle(
        "InvoiceValueRight",
        parent=sample_styles["Normal"],
        fontName=NUM_FONT,
        fontSize=8,
        leading=10,
        textColor=DARK,
        alignment=TA_RIGHT,
    )

    buyer = getattr(invoice, "buyer", None)
    contract_document = getattr(invoice, "contract_document", None)
    contract = getattr(invoice, "contract", None) or (
        contract_document.contract
        if contract_document and getattr(contract_document, "contract", None)
        else None
    )
    batch = (
        getattr(invoice, "commercial_processing_batch", None)
        or getattr(invoice, "processing_batch", None)
        or getattr(invoice, "batch", None)
    )

    currency = getattr(invoice, "currency", None) or "USD"
    invoice_no = _invoice_number(invoice)
    invoice_status = status_label(getattr(invoice, "status", "issued"))
    issue_date = fmt_date(_invoice_date(invoice))

    subtotal = decimalize(getattr(invoice, "subtotal", 0))
    tax = decimalize(getattr(invoice, "tax", 0))
    total = decimalize(getattr(invoice, "total", 0))
    deposit_paid = decimalize(getattr(invoice, "deposit_paid", 0))
    balance_due = decimalize(getattr(invoice, "balance", total - deposit_paid))

    draw_header(
        c,
        title="COMMERCIAL INVOICE",
        right_line_1=f"No: {invoice_no}",
        right_line_2=f"Status: {invoice_status} | Issue: {issue_date}",
    )

    y = height - 44 * mm

    # Hero balance box
    hero_fill = GREEN_SOFT if balance_due <= 0 else GOLD_SOFT
    hero_border = GREEN_BORDER if balance_due <= 0 else GOLD

    c.setFillColor(hero_fill)
    c.setStrokeColor(hero_border)
    c.roundRect(18 * mm, y - 28 * mm, width - 36 * mm, 28 * mm, 8, stroke=1, fill=1)

    c.setFillColor(JUNGLE)
    c.setFont(TEXT_BOLD, 10)
    c.drawString(24 * mm, y - 9 * mm, "BALANCE DUE")

    c.setFont(NUM_BOLD, 21)
    c.drawString(24 * mm, y - 20 * mm, money(balance_due, currency))

    c.setFillColor(DARK)
    c.setFont(TEXT_FONT, 9)
    c.drawRightString(width - 24 * mm, y - 10 * mm, f"Invoice Total: {money(total, currency)}")
    c.drawRightString(width - 24 * mm, y - 17 * mm, f"Paid: {money(deposit_paid, currency)}")

    y -= 40 * mm

    # Buyer + references
    _draw_section_title(c, "Billed To", 18 * mm, y)
    _draw_section_title(c, "Commercial References", width / 2 + 2 * mm, y)
    y -= 6 * mm

    left_x = 18 * mm
    right_x = width / 2 + 2 * mm
    box_h = 48 * mm
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

    reference_rows = [
        ("Contract", _contract_ref(contract)),
        ("Document", _contract_document_ref(contract_document)),
        ("Batch", _batch_ref(batch)),
        ("Currency", currency),
        ("As At", fmt_date(today)),
    ]

    reference_data = [
        [p(f"{label}:", label_style), p(value, value_style)]
        for label, value in reference_rows
    ]

    reference_table = Table(
        reference_data,
        colWidths=[25 * mm, right_w - 33 * mm],
        hAlign="LEFT",
    )

    reference_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    _, reference_h = reference_table.wrapOn(c, right_w - 8 * mm, box_h - 8 * mm)
    reference_table.drawOn(c, right_x + 4 * mm, y - 6 * mm - reference_h)

    y -= box_h + 14 * mm

    # Invoice items
    _draw_section_title(c, "Invoice Items", 18 * mm, y)
    y -= 7 * mm

    item_data = [[
        p("Description", styles["white_header"]),
        p("Qty", styles["white_header_right"]),
        p("Unit Price", styles["white_header_right"]),
        p("Line Total", styles["white_header_right"]),
    ]]

    items = list(getattr(invoice, "items", []) or [])

    for item in items:
        description = getattr(item, "description", None) or "-"
        quantity = decimalize(getattr(item, "quantity", 0))
        unit_price = decimalize(getattr(item, "unit_price", 0))
        line_total = decimalize(getattr(item, "line_total", quantity * unit_price))

        item_data.append([
            p(description, styles["small_dark"]),
            p(f"{quantity:,.2f}", value_right_style),
            p(f"{unit_price:,.2f}", value_right_style),
            p(f"{line_total:,.2f}", value_right_style),
        ])

    if not items:
        item_data.append([
            p("No invoice items found", styles["small_dark"]),
            p("-", value_right_style),
            p("-", value_right_style),
            p("-", value_right_style),
        ])

    item_table = Table(
        item_data,
        colWidths=[94 * mm, 25 * mm, 31 * mm, 31 * mm],
        hAlign="LEFT",
        repeatRows=1,
    )

    item_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), JUNGLE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    _, item_table_h = item_table.wrapOn(c, width - 36 * mm, y)

    if y - item_table_h < 72 * mm:
        c.showPage()
        y = height - 24 * mm

    item_table.drawOn(c, 18 * mm, y - item_table_h)
    y = y - item_table_h - 14 * mm

    # Totals + terms
    totals_box_w = 88 * mm
    totals_box_x = width - 18 * mm - totals_box_w
    totals_box_h = 52 * mm
    totals_box_y = y - totals_box_h

    terms_x = 18 * mm
    terms_w = totals_box_x - terms_x - 10 * mm

    c.setFillColor(colors.white)
    c.setStrokeColor(BORDER)
    c.roundRect(terms_x, totals_box_y, terms_w, totals_box_h, 6, stroke=1, fill=1)

    c.setFillColor(DARK)
    c.setFont(TEXT_BOLD, 10)
    c.drawString(terms_x + 4 * mm, y - 8 * mm, "Terms & Payment Notes")

    terms = _terms_from_invoice_or_contract(invoice, contract)
    notes = getattr(invoice, "notes", None)

    terms_text = terms
    if notes:
        terms_text = f"{terms} Notes: {notes}"

    terms_para = Paragraph(safe_text(terms_text), note_style)
    _, terms_h = terms_para.wrap(terms_w - 8 * mm, totals_box_h - 16 * mm)
    terms_para.drawOn(c, terms_x + 4 * mm, y - 15 * mm - terms_h)

    c.setFillColor(LIGHT)
    c.setStrokeColor(BORDER)
    c.roundRect(totals_box_x, totals_box_y, totals_box_w, totals_box_h, 6, stroke=1, fill=1)

    total_rows = [
        ("Subtotal", subtotal, False),
        ("Tax", tax, False),
        ("Total Invoice Value", total, True),
        ("Paid / Deposits", deposit_paid, False),
        ("Balance Due", balance_due, True),
    ]

    row_y = y - 9 * mm
    label_x = totals_box_x + 5 * mm
    value_x = totals_box_x + totals_box_w - 5 * mm

    for label, value, bold in total_rows:
        c.setFillColor(JUNGLE if label == "Balance Due" else DARK)
        c.setFont(TEXT_BOLD if bold else TEXT_FONT, 9)
        c.drawString(label_x, row_y, label)

        c.setFont(NUM_BOLD if bold else NUM_FONT, 9)
        c.drawRightString(value_x, row_y, money(value, currency))

        row_y -= 9 * mm

    y = totals_box_y - 14 * mm

    # Signature / authorization block
    sign_h = 28 * mm

    if y - sign_h < 24 * mm:
        c.showPage()
        y = height - 24 * mm

    c.setFillColor(colors.white)
    c.setStrokeColor(BORDER)
    c.roundRect(18 * mm, y - sign_h, width - 36 * mm, sign_h, 6, stroke=1, fill=1)

    c.setFillColor(DARK)
    c.setFont(TEXT_BOLD, 10)
    c.drawString(22 * mm, y - 8 * mm, "Authorization")

    c.setFillColor(GRAY)
    c.setFont(TEXT_FONT, 8.5)
    c.drawString(22 * mm, y - 16 * mm, "Prepared by Rizara Meats Ltd")

    c.setStrokeColor(BORDER)
    c.line(width - 72 * mm, y - 18 * mm, width - 22 * mm, y - 18 * mm)

    c.setFillColor(GRAY)
    c.setFont(TEXT_FONT, 8)
    c.drawString(width - 72 * mm, y - 23 * mm, "Authorized Signature")

    c.showPage()
    c.save()

    pdf = buffer.getvalue()
    buffer.close()

    return pdf