# /home/thumbi/rizara/app/utils/pdf_theme.py

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


JUNGLE = colors.HexColor("#1f6f54")
GOLD = colors.HexColor("#d4af37")
DARK = colors.HexColor("#111827")
GRAY = colors.HexColor("#6b7280")
LIGHT = colors.HexColor("#f9fafb")
BORDER = colors.HexColor("#e5e7eb")
GREEN_SOFT = colors.HexColor("#ecfdf5")
GREEN_BORDER = colors.HexColor("#bbf7d0")
GOLD_SOFT = colors.HexColor("#fffbeb")


TEXT_FONT = "Helvetica"
TEXT_BOLD = "Helvetica-Bold"
NUM_FONT = "Courier"
NUM_BOLD = "Courier-Bold"


def fmt_date(value, with_time: bool = False) -> str:
    if not value:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M") if with_time else value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value)


def decimalize(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0.00")


def money(value, currency: str = "USD") -> str:
    return f"{currency} {decimalize(value):,.2f}"


def safe_text(value) -> str:
    return str(value or "-").replace("&", "&amp;")


def p(value, style):
    return Paragraph(safe_text(value), style)


def status_label(value) -> str:
    try:
        value = value.value
    except Exception:
        value = str(value or "-")
    return value.replace("_", " ").title()


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, footer_func=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self.footer_func = footer_func

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_page_states)

        for page_num, state in enumerate(self._saved_page_states, start=1):
            self.__dict__.update(state)

            if self.footer_func:
                self.footer_func(self, page_num, total_pages)

            canvas.Canvas.showPage(self)

        canvas.Canvas.save(self)


def draw_footer(c, page_num: int, total_pages: int):
    width, _ = A4

    c.setFillColor(colors.HexColor("#e5e7eb"))
    c.rect(0, 0, width, 14 * mm, stroke=0, fill=1)

    c.setFillColor(colors.HexColor("#374151"))
    c.setFont(TEXT_FONT, 8)
    c.drawString(
        18 * mm,
        5 * mm,
        "Rizara Meats Ltd - Nairobi, Kenya - sales@rizarameats.co.ke",
    )

    c.setFillColor(colors.HexColor("#6b7280"))
    c.setFont(NUM_FONT, 8)
    c.drawRightString(width - 18 * mm, 5 * mm, f"Page {page_num} of {total_pages}")


def make_styles():
    styles = getSampleStyleSheet()

    return {
        "small_gray": ParagraphStyle(
            "SmallGray",
            parent=styles["Normal"],
            fontName=TEXT_FONT,
            fontSize=7.5,
            leading=9,
            textColor=GRAY,
            alignment=TA_LEFT,
        ),
        "small_dark": ParagraphStyle(
            "SmallDark",
            parent=styles["Normal"],
            fontName=TEXT_FONT,
            fontSize=7.5,
            leading=9,
            textColor=DARK,
            alignment=TA_LEFT,
        ),
        "small_right": ParagraphStyle(
            "SmallRight",
            parent=styles["Normal"],
            fontName=NUM_FONT,
            fontSize=7.5,
            leading=9,
            textColor=DARK,
            alignment=TA_RIGHT,
        ),
        "white_header": ParagraphStyle(
            "WhiteHeader",
            parent=styles["Normal"],
            fontName=TEXT_BOLD,
            fontSize=7.6,
            leading=9,
            textColor=colors.white,
            alignment=TA_LEFT,
        ),
        "white_header_right": ParagraphStyle(
            "WhiteHeaderRight",
            parent=styles["Normal"],
            fontName=TEXT_BOLD,
            fontSize=7.6,
            leading=9,
            textColor=colors.white,
            alignment=TA_RIGHT,
        ),
        "white_total": ParagraphStyle(
            "WhiteTotal",
            parent=styles["Normal"],
            fontName=TEXT_BOLD,
            fontSize=7.6,
            leading=9,
            textColor=colors.white,
            alignment=TA_LEFT,
        ),
        "white_total_right": ParagraphStyle(
            "WhiteTotalRight",
            parent=styles["Normal"],
            fontName=NUM_BOLD,
            fontSize=7.6,
            leading=9,
            textColor=colors.white,
            alignment=TA_RIGHT,
        ),
        "note": ParagraphStyle(
            "Note",
            parent=styles["Normal"],
            fontName=TEXT_FONT,
            fontSize=8.5,
            leading=10.5,
            textColor=GRAY,
            alignment=TA_LEFT,
        ),
    }


def draw_header(c, *, title: str, right_line_1: str, right_line_2: str | None = None):
    width, height = A4

    c.setFillColor(JUNGLE)
    c.rect(0, height - 32 * mm, width, 32 * mm, stroke=0, fill=1)

    c.setFillColor(colors.white)
    c.setFont(TEXT_BOLD, 16)
    c.drawString(18 * mm, height - 15 * mm, "Rizara Meats Ltd")

    c.setFont(TEXT_FONT, 9)
    c.drawString(18 * mm, height - 22 * mm, "Ethical - Traceable - Halal")

    c.setFont(TEXT_BOLD, 12)
    c.drawRightString(width - 18 * mm, height - 14 * mm, title)

    c.setFont(TEXT_FONT, 9)
    c.drawRightString(width - 18 * mm, height - 20 * mm, right_line_1)

    if right_line_2:
        c.drawRightString(width - 18 * mm, height - 25 * mm, right_line_2)