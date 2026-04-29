# /home/thumbi/rizara/app/utils/customer_statement_pdf.py

from __future__ import annotations

import io
from datetime import date, datetime
from decimal import Decimal
from typing import Any

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


def _invoice_date(invoice: Any):
    return (
        getattr(invoice, "issue_date", None)
        or getattr(invoice, "invoice_date", None)
        or getattr(invoice, "issued_at", None)
        or getattr(invoice, "created_at", None)
    )


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _invoice_age_days(invoice: Any, today: date) -> int:
    invoice_date = _as_date(_invoice_date(invoice))
    if not invoice_date:
        return 0
    return max((today - invoice_date).days, 0)


def _age_bucket(days_old: int) -> str:
    if days_old <= 0:
        return "current"
    if days_old <= 30:
        return "1_30"
    if days_old <= 60:
        return "31_60"
    if days_old <= 90:
        return "61_90"
    return "90_plus"


def _currency(invoice: Any, fallback: str = "USD") -> str:
    return getattr(invoice, "currency", None) or fallback


def _invoice_number(invoice: Any) -> str:
    return getattr(invoice, "invoice_number", None) or f"INV-{getattr(invoice, 'id', '-')}"


def _compact_status(value: Any) -> str:
    status = status_label(value)
    return (
        status.replace("Partially Paid", "Partial")
        .replace("Fully Paid", "Paid")
        .replace("Payment Received", "Receipt")
    )


def _receipt_number(payment: Any) -> str:
    receipt_no = getattr(payment, "receipt_number", None)
    if receipt_no:
        return str(receipt_no)

    paid_at = getattr(payment, "paid_at", None)
    year = paid_at.year if isinstance(paid_at, (date, datetime)) else date.today().year
    payment_id = getattr(payment, "id", None)

    if payment_id:
        return f"RCT-{year}-{payment_id:05d}"

    return "-"


def _compact_receipt_number(payment: Any) -> str:
    receipt_no = _receipt_number(payment)

    if receipt_no == "-":
        return "Receipt"

    if len(receipt_no) > 11:
        return f"RCT {receipt_no[-5:]}"

    return receipt_no


def _payment_date(payment: Any):
    return (
        getattr(payment, "paid_at", None)
        or getattr(payment, "payment_date", None)
        or getattr(payment, "created_at", None)
    )


def _payment_amount(payment: Any) -> Decimal:
    return decimalize(
        getattr(payment, "amount", None)
        or getattr(payment, "paid_amount", None)
        or getattr(payment, "payment_amount", None)
        or 0
    )


def _safe_relationship_list(value) -> list[Any]:
    if not value:
        return []

    try:
        return list(value)
    except TypeError:
        return []


def _invoice_payments(invoice: Any) -> list[Any]:
    for name in [
        "payments",
        "sale_payments",
        "invoice_payments",
        "receipts",
        "payment_receipts",
    ]:
        payments = _safe_relationship_list(getattr(invoice, name, None))
        if payments:
            return payments

    return []


def _draw_section_title(c, title: str, x: float, y: float):
    c.setFillColor(DARK)
    c.setFont(TEXT_BOLD, 11)
    c.drawString(x, y, title)


def _new_page(c, height: float) -> float:
    c.showPage()
    return height - 24 * mm


def render_customer_statement_pdf(buyer, invoices) -> bytes:
    buffer = io.BytesIO()
    c = NumberedCanvas(buffer, pagesize=A4, footer_func=draw_footer)

    width, height = A4
    today = date.today()
    sample_styles = getSampleStyleSheet()

    value_style = ParagraphStyle(
        "StatementValue",
        parent=sample_styles["Normal"],
        fontName=TEXT_FONT,
        fontSize=7.4,
        leading=8.8,
        textColor=DARK,
        alignment=TA_LEFT,
        wordWrap="LTR",
        splitLongWords=False,
    )

    muted_style = ParagraphStyle(
        "StatementMutedValue",
        parent=sample_styles["Normal"],
        fontName=TEXT_FONT,
        fontSize=7.1,
        leading=8.5,
        textColor=GRAY,
        alignment=TA_LEFT,
        wordWrap="LTR",
        splitLongWords=False,
    )

    number_style = ParagraphStyle(
        "StatementNumber",
        parent=sample_styles["Normal"],
        fontName=NUM_FONT,
        fontSize=7.2,
        leading=8.8,
        textColor=DARK,
        alignment=TA_RIGHT,
        wordWrap="LTR",
        splitLongWords=False,
    )

    note_style = ParagraphStyle(
        "StatementNote",
        parent=sample_styles["Normal"],
        fontName=TEXT_FONT,
        fontSize=8.5,
        leading=10.5,
        textColor=GRAY,
        alignment=TA_LEFT,
    )

    white_header = ParagraphStyle(
        "StatementWhiteHeader",
        parent=sample_styles["Normal"],
        fontName=TEXT_BOLD,
        fontSize=7.2,
        leading=8.8,
        textColor=colors.white,
        alignment=TA_LEFT,
        wordWrap="LTR",
        splitLongWords=False,
    )

    white_header_right = ParagraphStyle(
        "StatementWhiteHeaderRight",
        parent=sample_styles["Normal"],
        fontName=TEXT_BOLD,
        fontSize=7.2,
        leading=8.8,
        textColor=colors.white,
        alignment=TA_RIGHT,
        wordWrap="LTR",
        splitLongWords=False,
    )

    white_total = ParagraphStyle(
        "StatementWhiteTotal",
        parent=sample_styles["Normal"],
        fontName=TEXT_BOLD,
        fontSize=7.2,
        leading=8.8,
        textColor=colors.white,
        alignment=TA_LEFT,
    )

    white_total_right = ParagraphStyle(
        "StatementWhiteTotalRight",
        parent=sample_styles["Normal"],
        fontName=NUM_BOLD,
        fontSize=7.2,
        leading=8.8,
        textColor=colors.white,
        alignment=TA_RIGHT,
    )

    invoices = list(invoices or [])

    statement_currency = "USD"
    if invoices:
        statement_currency = _currency(invoices[0], "USD")

    grand_total = Decimal("0.00")
    grand_paid = Decimal("0.00")
    grand_balance = Decimal("0.00")
    receipt_total = Decimal("0.00")

    aging = {
        "current": Decimal("0.00"),
        "1_30": Decimal("0.00"),
        "31_60": Decimal("0.00"),
        "61_90": Decimal("0.00"),
        "90_plus": Decimal("0.00"),
    }

    for invoice in invoices:
        total = decimalize(getattr(invoice, "total", 0))
        paid = decimalize(getattr(invoice, "deposit_paid", 0))
        balance = decimalize(getattr(invoice, "balance", 0))

        grand_total += total
        grand_paid += paid
        grand_balance += balance

        payments = _invoice_payments(invoice)
        for payment in payments:
            receipt_total += _payment_amount(payment)

        if balance > 0:
            days_old = _invoice_age_days(invoice, today)
            aging[_age_bucket(days_old)] += balance

    if receipt_total <= 0:
        receipt_total = grand_paid

    buyer_name = getattr(buyer, "name", "-") if buyer else "-"
    buyer_email = getattr(buyer, "email", None) or "-"
    buyer_phone = getattr(buyer, "phone", None) or "-"
    buyer_address = getattr(buyer, "address", None) or ""

    draw_header(
        c,
        title="CUSTOMER STATEMENT",
        right_line_1=f"As at: {fmt_date(today)}",
        right_line_2=f"Currency: {statement_currency}",
    )

    y = height - 44 * mm

    # Outstanding balance hero
    hero_fill = GREEN_SOFT if grand_balance <= 0 else GOLD_SOFT
    hero_border = GREEN_BORDER if grand_balance <= 0 else GOLD

    c.setFillColor(hero_fill)
    c.setStrokeColor(hero_border)
    c.roundRect(18 * mm, y - 28 * mm, width - 36 * mm, 28 * mm, 8, stroke=1, fill=1)

    c.setFillColor(JUNGLE)
    c.setFont(TEXT_BOLD, 10)
    c.drawString(24 * mm, y - 9 * mm, "OUTSTANDING BALANCE")

    c.setFont(NUM_BOLD, 21)
    c.drawString(24 * mm, y - 20 * mm, money(grand_balance, statement_currency))

    c.setFillColor(DARK)
    c.setFont(TEXT_FONT, 9)
    c.drawRightString(width - 24 * mm, y - 10 * mm, f"Buyer: {str(buyer_name)[:42]}")
    c.drawRightString(width - 24 * mm, y - 17 * mm, "Statement Status: Open")

    y -= 40 * mm

    # Customer + financial summary
    _draw_section_title(c, "Customer Details", 18 * mm, y)
    _draw_section_title(c, "Financial Summary", width / 2 + 2 * mm, y)
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

    c.setFillColor(DARK)
    c.setFont(TEXT_BOLD, 10)
    c.drawString(left_x + 4 * mm, y - 8 * mm, str(buyer_name)[:44])

    c.setFont(TEXT_FONT, 9)
    buyer_y = y - 16 * mm

    for text in [buyer_email, buyer_phone, buyer_address]:
        if text:
            c.drawString(left_x + 4 * mm, buyer_y, str(text)[:55])
            buyer_y -= 7 * mm

    summary_rows = [
        ("Total Invoiced", grand_total, False),
        ("Total Paid / Receipts", receipt_total, False),
        ("Outstanding Balance", grand_balance, True),
    ]

    row_y = y - 10 * mm

    for label, amount, bold in summary_rows:
        c.setFillColor(JUNGLE if bold else DARK)
        c.setFont(TEXT_BOLD if bold else TEXT_FONT, 9)
        c.drawString(right_x + 5 * mm, row_y, label)

        c.setFont(NUM_BOLD if bold else NUM_FONT, 9)
        c.drawRightString(right_x + right_w - 5 * mm, row_y, money(amount, statement_currency))

        row_y -= 10 * mm

    y -= box_h + 14 * mm

    # Aging summary
    _draw_section_title(c, "Debt Aging Summary", 18 * mm, y)
    y -= 7 * mm

    aging_data = [
        [
            p("Current", white_header),
            p("1-30 Days", white_header),
            p("31-60 Days", white_header),
            p("61-90 Days", white_header),
            p("90+ Days", white_header),
        ],
        [
            p(money(aging["current"], statement_currency), number_style),
            p(money(aging["1_30"], statement_currency), number_style),
            p(money(aging["31_60"], statement_currency), number_style),
            p(money(aging["61_90"], statement_currency), number_style),
            p(money(aging["90_plus"], statement_currency), number_style),
        ],
    ]

    aging_table = Table(
        aging_data,
        colWidths=[(width - 36 * mm) / 5] * 5,
        hAlign="LEFT",
    )

    aging_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), JUNGLE),
        ("BACKGROUND", (0, 1), (-1, 1), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    _, aging_h = aging_table.wrapOn(c, width - 36 * mm, y)
    aging_table.drawOn(c, 18 * mm, y - aging_h)
    y = y - aging_h - 14 * mm

    # Bank-grade ledger activity
    _draw_section_title(c, "Statement Activity", 18 * mm, y)
    y -= 7 * mm

    statement_data = [[
        p("Date", white_header),
        p("Document", white_header),
        p("Cur", white_header),
        p("Debit", white_header_right),
        p("Credit", white_header_right),
        p("Run. Bal.", white_header_right),
        p("Status", white_header),
    ]]

    running_balance = Decimal("0.00")

    for invoice in invoices:
        inv_currency = _currency(invoice, statement_currency)
        total = decimalize(getattr(invoice, "total", 0))
        invoice_balance = decimalize(getattr(invoice, "balance", 0))
        deposit_paid = decimalize(getattr(invoice, "deposit_paid", 0))
        payments = _invoice_payments(invoice)

        running_balance += total

        statement_data.append([
            p(fmt_date(_invoice_date(invoice)), value_style),
            p(_invoice_number(invoice), value_style),
            p(inv_currency, value_style),
            p(f"{total:,.2f}", number_style),
            p("-", number_style),
            p(f"{running_balance:,.2f}", number_style),
            p(_compact_status(getattr(invoice, "status", "-")), value_style),
        ])

        for payment in payments:
            amount = _payment_amount(payment)
            running_balance -= amount

            statement_data.append([
                p(fmt_date(_payment_date(payment), with_time=True), muted_style),
                p(_compact_receipt_number(payment), muted_style),
                p(inv_currency, muted_style),
                p("-", number_style),
                p(f"{amount:,.2f}", number_style),
                p(f"{running_balance:,.2f}", number_style),
                p("Receipt", muted_style),
            ])

        if not payments and deposit_paid > 0:
            running_balance -= deposit_paid

            statement_data.append([
                p(fmt_date(_invoice_date(invoice)), muted_style),
                p("Receipt", muted_style),
                p(inv_currency, muted_style),
                p("-", number_style),
                p(f"{deposit_paid:,.2f}", number_style),
                p(f"{running_balance:,.2f}", number_style),
                p("Receipt", muted_style),
            ])

    statement_data.append([
        p("-", white_total),
        p("TOTAL", white_total),
        p(statement_currency, white_total),
        p(f"{grand_total:,.2f}", white_total_right),
        p(f"{receipt_total:,.2f}", white_total_right),
        p(f"{grand_balance:,.2f}", white_total_right),
        p("-", white_total),
    ])

    # Total width = 174mm. Fits exactly within 18mm left/right margins on A4.
    statement_table = Table(
        statement_data,
        colWidths=[
            22 * mm,  # Date
            39 * mm,  # Document
            10 * mm,  # Cur
            24 * mm,  # Debit
            24 * mm,  # Credit
            28 * mm,  # Running Balance
            27 * mm,  # Status
        ],
        repeatRows=1,
        hAlign="LEFT",
    )

    statement_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), JUNGLE),
        ("BACKGROUND", (0, -1), (-1, -1), JUNGLE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1.6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    _, table_h = statement_table.wrapOn(c, width - 36 * mm, y)

    if y - table_h < 48 * mm:
        y = _new_page(c, height)

    statement_table.drawOn(c, 18 * mm, y - table_h)
    y = y - table_h - 14 * mm

    # Statement note
    note_h = 34 * mm

    if y - note_h < 24 * mm:
        y = _new_page(c, height)

    c.setFillColor(colors.white)
    c.setStrokeColor(BORDER)
    c.roundRect(18 * mm, y - note_h, width - 36 * mm, note_h, 6, stroke=1, fill=1)

    c.setFillColor(DARK)
    c.setFont(TEXT_BOLD, 10)
    c.drawString(22 * mm, y - 8 * mm, "Statement Note")

    note_text = (
        "This bank-grade ledger statement records invoices as debits and receipts as credits, "
        "with a running balance after each transaction. Debt aging is calculated from the invoice "
        "issue date and applies only to unpaid balances."
    )

    note_para = Paragraph(safe_text(note_text), note_style)
    _, wrapped_note_h = note_para.wrap(width - 48 * mm, 20 * mm)
    note_para.drawOn(c, 22 * mm, y - 14 * mm - wrapped_note_h)

    c.showPage()
    c.save()

    pdf = buffer.getvalue()
    buffer.close()

    return pdf