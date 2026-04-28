from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet


def money(value):
    return Decimal(str(value or 0))


def render_customer_statement_pdf(buyer, invoices) -> bytes:
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )

    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("<b>Rizara Meats Ltd</b>", styles["Title"]))
    story.append(Paragraph("Customer Statement", styles["Heading2"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph(f"<b>Buyer:</b> {buyer.name}", styles["Normal"]))
    story.append(Paragraph(f"<b>Email:</b> {buyer.email or '-'}", styles["Normal"]))
    story.append(Paragraph(f"<b>Phone:</b> {buyer.phone or '-'}", styles["Normal"]))
    story.append(Paragraph(f"<b>Generated:</b> {date.today()}", styles["Normal"]))
    story.append(Spacer(1, 14))

    data = [[
        "Date",
        "Invoice",
        "Currency",
        "Total",
        "Paid",
        "Balance",
        "Status",
    ]]

    grand_total = Decimal("0.00")
    grand_paid = Decimal("0.00")
    grand_balance = Decimal("0.00")

    for invoice in invoices:
        currency = invoice.currency or "USD"
        total = money(invoice.total)
        paid = money(invoice.deposit_paid)
        balance = money(invoice.balance)

        grand_total += total
        grand_paid += paid
        grand_balance += balance

        status = invoice.status.value if hasattr(invoice.status, "value") else str(invoice.status)

        data.append([
            str(invoice.issue_date),
            invoice.invoice_number,
            currency,
            f"{total:,.2f}",
            f"{paid:,.2f}",
            f"{balance:,.2f}",
            status.replace("_", " ").title(),
        ])

    data.append([
        "",
        "TOTAL",
        "",
        f"{grand_total:,.2f}",
        f"{grand_paid:,.2f}",
        f"{grand_balance:,.2f}",
        "",
    ])

    table = Table(
        data,
        colWidths=[24 * mm, 32 * mm, 20 * mm, 28 * mm, 28 * mm, 28 * mm, 28 * mm],
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e5e7eb")),
        ("ALIGN", (3, 1), (5, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))

    story.append(table)
    doc.build(story)

    pdf = buffer.getvalue()
    buffer.close()
    return pdf