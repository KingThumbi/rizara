# app/services/document_renderer.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from flask import current_app, render_template
from weasyprint import HTML

from app.config.company import (
    COMPANY_NAME,
    COMPANY_TAGLINE,
    COMPANY_ADDRESS,
    COMPANY_EMAIL,
    COMPANY_PHONE,
    COMPANY_WEBSITE,
)

EAT = ZoneInfo("Africa/Nairobi")


def _now_eat() -> datetime:
    return datetime.now(EAT)


def _company() -> dict[str, str]:
    # Keep it simple: a dict is enough for templates
    return {
        "name": COMPANY_NAME,
        "tagline": COMPANY_TAGLINE,
        "address": COMPANY_ADDRESS,
        "email": COMPANY_EMAIL,
        "phone": COMPANY_PHONE,
        "website": COMPANY_WEBSITE,
    }


def _doc_title(document: Any) -> str:
    dt = (getattr(document, "doc_type", "") or "").strip().lower()
    if dt == "export_sales_contract":
        return "Export Sales Contract"
    if dt == "loi":
        return "Letter of Intent"
    if dt:
        return dt.replace("_", " ").title()
    return "Document"


def _doc_ref(document: Any) -> str:
    """
    Human-friendly reference displayed on PDFs.
    Example: EXPORT_SALES_CONTRACT / <uuid> / v1
    """
    doc_type = (getattr(document, "doc_type", "") or "").strip()
    doc_id = getattr(document, "id", None)
    version = getattr(document, "version", None)

    parts: list[str] = []
    if doc_type:
        parts.append(doc_type.upper())
    if doc_id:
        parts.append(str(doc_id))
    if version is not None:
        parts.append(f"v{version}")
    return " / ".join(parts) if parts else "RIZARA-DOC"


def _resolve_base_url(explicit: str | None) -> str:
    """
    WeasyPrint base_url helps resolve relative links (static assets).
    Best practice: pass request.url_root from the route.
    But we keep a safe fallback for CLI jobs / shell rendering.
    """
    if explicit:
        # normalize to trailing slash
        return explicit if explicit.endswith("/") else (explicit + "/")

    try:
        server = current_app.config.get("SERVER_NAME")
        scheme = current_app.config.get("PREFERRED_URL_SCHEME", "http")
        if server:
            return f"{scheme}://{server}/"
    except Exception:
        pass

    return "/"


def render_export_sales_contract_pdf_bytes(document: Any, base_url: str | None = None) -> bytes:
    """
    Returns PDF bytes for the export sales contract.
    No DB writes.
    """
    now_eat = _now_eat()
    html = render_template(
        "pdfs/export_sales_contract.html",
        document=document,
        now_eat=now_eat,
        company=_company(),
        doc_title=_doc_title(document),
        doc_ref=_doc_ref(document),
        doc_date=now_eat.strftime("%d %b %Y"),
    )
    return HTML(string=html, base_url=_resolve_base_url(base_url)).write_pdf()


def render_loi_pdf_bytes(document: Any, base_url: str | None = None) -> bytes:
    """
    Optional helper if/when you render LOI PDFs from a template.
    Keeps the same letterhead context for consistency.
    """
    now_eat = _now_eat()
    html = render_template(
        "pdfs/loi.html",
        document=document,
        now_eat=now_eat,
        company=_company(),
        doc_title="Letter of Intent",
        doc_ref=_doc_ref(document),
        doc_date=now_eat.strftime("%d %b %Y"),
    )
    return HTML(string=html, base_url=_resolve_base_url(base_url)).write_pdf()