# app/utils/document_pdf.py
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

from app.utils.pdf_theme import (
    NumberedCanvas,
    draw_footer,
    draw_header,
    fmt_date,
    decimalize,
    money,
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


def _doc_date(doc):
    return (
        getattr(doc, "issued_at", None)
        or getattr(doc, "created_at", None)
        or date.today()
    )


def _doc_number(doc, payload: dict) -> str:
    return (
        payload.get("document_number")
        or payload.get("proforma_number")
        or f"DOC-{getattr(doc, 'id', '')}"
    )


def _doc_title(doc, payload: dict) -> str:
    return (
        payload.get("document_title")
        or str(getattr(doc, "doc_type", "document")).replace("_", " ").title()
    )


def _buyer_value(doc, payload: dict, field: str, default: str = "") -> str:
    buyer = getattr(doc, "buyer", None)
    return (
        payload.get(f"buyer_{field}")
        or (getattr(buyer, field, None) if buyer else None)
        or default
    )


def _terms_note(doc, payload: dict) -> str:
    note = payload.get("terms_note")
    if note:
        return str(note)

    if getattr(doc, "doc_type", "") == "proforma_invoice":
        return (
            "This Proforma Invoice is issued for quotation, payment processing, "
            "and contract fulfilment planning. It is not a tax invoice."
        )

    return "Payment and delivery terms apply as agreed."


def _draw_section_title(c, title: str, x: float, y: float):
    c.setFillColor(DARK)
    c.setFont(TEXT_BOLD, 11)
    c.drawString(x, y, title)


def render_document_invoice_pdf(doc) -> bytes:
    """
    Render Rizara document invoices such as Proforma Invoice and Commercial Invoice
    using the same visual quality as invoice_pdf.py.
    """
    payload = doc.payload or {}

    buffer = io.BytesIO()
    c = NumberedCanvas(buffer, pagesize=A4, footer_func=draw_footer)

    width, height = A4
    today = date.today()
    styles = make_styles()
    sample_styles = getSampleStyleSheet()

    note_style = ParagraphStyle(
        "DocumentInvoiceNote",
        parent=sample_styles["Normal"],
        fontName=TEXT_FONT,
        fontSize=8.5,
        leading=10.5,
        textColor=GRAY,
        alignment=TA_LEFT,
    )

    label_style = ParagraphStyle(
        "DocumentInvoiceLabel",
        parent=sample_styles["Normal"],
        fontName=TEXT_FONT,
        fontSize=8,
        leading=10,
        textColor=GRAY,
        alignment=TA_LEFT,
    )

    value_style = ParagraphStyle(
        "DocumentInvoiceValue",
        parent=sample_styles["Normal"],
        fontName=TEXT_FONT,
        fontSize=8,
        leading=10,
        textColor=DARK,
        alignment=TA_LEFT,
    )

    value_right_style = ParagraphStyle(
        "DocumentInvoiceValueRight",
        parent=sample_styles["Normal"],
        fontName=NUM_FONT,
        fontSize=8,
        leading=10,
        textColor=DARK,
        alignment=TA_RIGHT,
    )

    currency = payload.get("currency") or "USD"
    title = _doc_title(doc, payload).upper()
    document_no = _doc_number(doc, payload)
    issue_date = fmt_date(_doc_date(doc))
    status = str(payload.get("status") or getattr(doc, "status", "draft")).replace("_", " ").title()

    subtotal = decimalize(payload.get("subtotal", 0))
    discount = decimalize(payload.get("discount", 0))
    shipping = decimalize(payload.get("shipping", 0))
    tax = decimalize(payload.get("tax", 0))
    grand_total = decimalize(payload.get("grand_total", subtotal - discount + shipping + tax))

    amount_received = decimalize(payload.get("amount_received", 0))
    balance_due = decimalize(payload.get("balance_due", grand_total - amount_received))

    buyer_name = _buyer_value(doc, payload, "name", "-")
    buyer_phone = _buyer_value(doc, payload, "phone", "")
    buyer_email = _buyer_value(doc, payload, "email", "")
    buyer_address = _buyer_value(doc, payload, "address", "")

    contract_number = payload.get("contract_number") or "-"
    destination = payload.get("destination_country") or "TBA"
    price_basis = payload.get("price_basis") or "As agreed"
    payment_terms = payload.get("payment_terms") or "As agreed"
    delivery_terms = payload.get("delivery_terms") or "As agreed"

    draw_header(
        c,
        title=title,
        right_line_1=f"No: {document_no}",
        right_line_2=f"Status: {status} | Issue: {issue_date}",
    )

    y = height - 44 * mm

    hero_fill = GREEN_SOFT if getattr(doc, "doc_type", "") == "proforma_invoice" else GOLD_SOFT
    hero_border = GREEN_BORDER if getattr(doc, "doc_type", "") == "proforma_invoice" else GOLD
    hero_label = "PROFORMA VALUE" if getattr(doc, "doc_type", "") == "proforma_invoice" else "DOCUMENT VALUE"

    c.setFillColor(hero_fill)
    c.setStrokeColor(hero_border)
    c.roundRect(18 * mm, y - 28 * mm, width - 36 * mm, 28 * mm, 8, stroke=1, fill=1)

    c.setFillColor(JUNGLE)
    c.setFont(TEXT_BOLD, 10)
    c.drawString(24 * mm, y - 9 * mm, hero_label)

    c.setFont(NUM_BOLD, 21)
    c.drawString(24 * mm, y - 20 * mm, money(grand_total, currency))

    c.setFillColor(DARK)
    c.setFont(TEXT_FONT, 9)
    c.drawRightString(width - 24 * mm, y - 10 * mm, f"Currency: {currency}")
    c.drawRightString(width - 24 * mm, y - 17 * mm, f"Price Basis: {price_basis}")

    y -= 40 * mm

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

    c.setFillColor(DARK)
    c.setFont(TEXT_BOLD, 10)
    c.drawString(left_x + 4 * mm, y - 8 * mm, str(buyer_name)[:44])

    c.setFont(TEXT_FONT, 9)
    buyer_y = y - 15 * mm
    for text in [buyer_phone, buyer_email, buyer_address, destination]:
        if text:
            c.drawString(left_x + 4 * mm, buyer_y, str(text)[:55])
            buyer_y -= 6 * mm

    reference_rows = [
        ("Contract", contract_number),
        ("Destination", destination),
        ("Payment", payment_terms),
        ("Delivery", delivery_terms),
        ("Currency", currency),
        ("As At", fmt_date(today)),
    ]

    reference_data = [
        [p(f"{label}:", label_style), p(str(value), value_style)]
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

    section_title = "Proforma Items" if getattr(doc, "doc_type", "") == "proforma_invoice" else "Document Items"
    _draw_section_title(c, section_title, 18 * mm, y)
    y -= 7 * mm

    item_data = [[
        p("Description", styles["white_header"]),
        p("Qty", styles["white_header_right"]),
        p("Unit Price", styles["white_header_right"]),
        p("Line Total", styles["white_header_right"]),
    ]]

    items = payload.get("items") or []

    for item in items:
        description = item.get("description") or item.get("product_name") or "Processed Halal Meat"
        if item.get("quality_spec"):
            description = f"{description}<br/><font color='#6b7280'>{safe_text(item.get('quality_spec'))}</font>"

        quantity = decimalize(item.get("quantity", 0))
        unit = item.get("unit_of_measure") or "kg"
        unit_price = decimalize(item.get("unit_price", 0))
        line_total = decimalize(item.get("line_total", quantity * unit_price))

        item_data.append([
            p(description, styles["small_dark"]),
            p(f"{quantity:,.2f} {unit}", value_right_style),
            p(f"{unit_price:,.2f}", value_right_style),
            p(f"{line_total:,.2f}", value_right_style),
        ])

    if not items:
        product = payload.get("product_type") or "Processed Halal Meat"
        quantity = decimalize(payload.get("quantity_kg", 0))
        unit_price = decimalize(payload.get("unit_price", 0))

        item_data.append([
            p(product, styles["small_dark"]),
            p(f"{quantity:,.2f} kg", value_right_style),
            p(f"{unit_price:,.2f}", value_right_style),
            p(f"{grand_total:,.2f}", value_right_style),
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

    if y - item_table_h < 74 * mm:
        c.showPage()
        y = height - 24 * mm

    item_table.drawOn(c, 18 * mm, y - item_table_h)
    y = y - item_table_h - 14 * mm

    totals_box_w = 88 * mm
    totals_box_x = width - 18 * mm - totals_box_w
    totals_box_h = 52 * mm if amount_received > 0 else 43 * mm
    totals_box_y = y - totals_box_h

    terms_x = 18 * mm
    terms_w = totals_box_x - terms_x - 10 * mm

    c.setFillColor(colors.white)
    c.setStrokeColor(BORDER)
    c.roundRect(terms_x, totals_box_y, terms_w, totals_box_h, 6, stroke=1, fill=1)

    c.setFillColor(DARK)
    c.setFont(TEXT_BOLD, 10)
    c.drawString(terms_x + 4 * mm, y - 8 * mm, "Terms & Payment Notes")

    terms_para = Paragraph(safe_text(_terms_note(doc, payload)), note_style)
    _, terms_h = terms_para.wrap(terms_w - 8 * mm, totals_box_h - 16 * mm)
    terms_para.drawOn(c, terms_x + 4 * mm, y - 15 * mm - terms_h)

    c.setFillColor(LIGHT)
    c.setStrokeColor(BORDER)
    c.roundRect(totals_box_x, totals_box_y, totals_box_w, totals_box_h, 6, stroke=1, fill=1)

    total_rows = [
        ("Subtotal", subtotal, False),
        ("Discount", discount, False),
        ("Shipping / Freight", shipping, False),
        ("Tax", tax, False),
        ("Total Proforma Value" if getattr(doc, "doc_type", "") == "proforma_invoice" else "Total Document Value", grand_total, True),
    ]

    if amount_received > 0:
        total_rows.extend([
            ("Paid / Deposits", amount_received, False),
            ("Balance Due", balance_due, True),
        ])

    row_y = y - 9 * mm
    label_x = totals_box_x + 5 * mm
    value_x = totals_box_x + totals_box_w - 5 * mm

    for label, value, bold in total_rows:
        c.setFillColor(JUNGLE if "Total" in label or label == "Balance Due" else DARK)
        c.setFont(TEXT_BOLD if bold else TEXT_FONT, 9)
        c.drawString(label_x, row_y, label)

        c.setFont(NUM_BOLD if bold else NUM_FONT, 9)
        c.drawRightString(value_x, row_y, money(value, currency))

        row_y -= 8 * mm

    y = totals_box_y - 14 * mm

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
