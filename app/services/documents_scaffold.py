# app/services/documents_scaffold.py
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

DOC_TYPE_LOI = "loi"
DOC_TYPE_EXPORT_SALES_CONTRACT = "export_sales_contract"

DOC_TYPE_OPTIONS = [
    (DOC_TYPE_LOI, "Letter of Intent (LOI)"),
    (DOC_TYPE_EXPORT_SALES_CONTRACT, "Export Sales Contract"),
]

DEFAULT_SCAFFOLDS = {
    DOC_TYPE_LOI: {
        "loi": {
            "buyer": {"name": "", "address": "", "country": "", "email": "", "phone": ""},
            "seller": {"name": "Rizara Meats", "address": "", "country": "Kenya"},
            "product": {"name": "Halal Goat Meat", "spec": "", "quantity_kg": 0},
            "pricing": {"price_per_kg": 0, "currency": "USD"},
            "incoterm": "CIF",
            "payment": {"advance_percent": 0, "balance_percent": 100, "notes": ""},
            "dates": {"issue_date": datetime.now(timezone.utc).date().isoformat()},
            "notes": "",
        }
    },
    DOC_TYPE_EXPORT_SALES_CONTRACT: {
        "contract": {
            "incoterm": "CIF",
            "governing_law": "Kenya",
            "dispute_resolution": "Negotiation → Arbitration",
            "notes": "",
        },
        "product": {
            "description": "Halal Goat Meat",
            "quantity_kg": 0,
            "packaging": "Chilled",
            "specs": "",
        },
        "pricing": {
            "price_per_kg": 0,
            "currency": "USD",
            "notes": "",
        },
        "payment": {
            "advance_percent": 50,
            "balance_percent": 50,
            "advance_required": True,
            "balance_due_before_shipment": True,
            "notes": "",
        },
        "buyer": {"name": "", "address": "", "country": "", "email": "", "phone": ""},
        "seller": {"name": "Rizara Meats", "address": "", "country": "Kenya"},
    },
}

DEFAULT_TITLES = {
    DOC_TYPE_LOI: "Letter of Intent",
    DOC_TYPE_EXPORT_SALES_CONTRACT: "Export Sales Contract",
}

def make_payload_scaffold(doc_type: str) -> dict:
    base = DEFAULT_SCAFFOLDS.get(doc_type)
    if not base:
        return {}
    return deepcopy(base)

def default_title_for(doc_type: str) -> str:
    return DEFAULT_TITLES.get(doc_type, "Document")

def next_admin_url_for(doc_type: str) -> str:
    """
    Return admin endpoint name to redirect after creation.

    NOTE: In this codebase the contract editor endpoint is:
      admin.documents_contract_edit
    (plural "documents")
    """
    if doc_type == DOC_TYPE_LOI:
        return "admin.documents_view"  # or your LOI edit/preview endpoint if you have one
    if doc_type == DOC_TYPE_EXPORT_SALES_CONTRACT:
        return "admin.documents_contract_edit"
    return "admin.documents_view"