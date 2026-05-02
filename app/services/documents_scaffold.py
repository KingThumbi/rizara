# app/services/documents_scaffold.py
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

DOC_TYPE_LOI = "loi"
DOC_TYPE_PROFORMA_INVOICE = "proforma_invoice"
DOC_TYPE_COMMERCIAL_INVOICE = "commercial_invoice"
DOC_TYPE_PACKING_LIST = "packing_list"

# Kept only for backward compatibility / old imports.
# New export sales contracts should be handled in the Contracts module.
DOC_TYPE_EXPORT_SALES_CONTRACT = "export_sales_contract"

DOC_TYPE_OPTIONS = [
    (DOC_TYPE_LOI, "Letter of Intent (LOI)"),
    (DOC_TYPE_PROFORMA_INVOICE, "Proforma Invoice"),
    (DOC_TYPE_COMMERCIAL_INVOICE, "Commercial Invoice"),
    (DOC_TYPE_PACKING_LIST, "Packing List"),
]

DEFAULT_SCAFFOLDS = {
    DOC_TYPE_LOI: {
        "loi": {
            "buyer": {
                "name": "",
                "address": "",
                "country": "",
                "email": "",
                "phone": "",
            },
            "seller": {
                "name": "Rizara Meats Ltd",
                "address": "",
                "country": "Kenya",
            },
            "product": {
                "name": "Halal Meat",
                "spec": "",
                "quantity_kg": 0,
            },
            "pricing": {
                "price_per_kg": 0,
                "currency": "USD",
            },
            "incoterm": "CIF",
            "payment": {
                "advance_percent": 0,
                "balance_percent": 100,
                "notes": "",
            },
            "dates": {
                "issue_date": datetime.now(timezone.utc).date().isoformat(),
            },
            "notes": "",
        }
    },

    DOC_TYPE_PROFORMA_INVOICE: {
        "proforma_invoice": {
            "buyer": {
                "name": "",
                "address": "",
                "country": "",
                "email": "",
                "phone": "",
                "tax_pin": "",
            },
            "seller": {
                "name": "Rizara Meats Ltd",
                "address": "",
                "country": "Kenya",
                "email": "",
                "phone": "",
                "tax_pin": "",
            },
            "invoice": {
                "number": "",
                "issue_date": datetime.now(timezone.utc).date().isoformat(),
                "valid_until": "",
                "currency": "USD",
                "incoterm": "CIF",
                "payment_terms": "",
            },
            "shipment": {
                "destination_country": "",
                "destination_port": "",
                "shipping_method": "",
            },
            "items": [
                {
                    "description": "Halal Meat",
                    "quantity_kg": 0,
                    "unit_price": 0,
                    "line_total": 0,
                }
            ],
            "totals": {
                "subtotal": 0,
                "tax": 0,
                "shipping": 0,
                "grand_total": 0,
            },
            "notes": "",
        }
    },

    DOC_TYPE_COMMERCIAL_INVOICE: {
        "commercial_invoice": {
            "buyer": {
                "name": "",
                "address": "",
                "country": "",
                "email": "",
                "phone": "",
                "tax_pin": "",
            },
            "seller": {
                "name": "Rizara Meats Ltd",
                "address": "",
                "country": "Kenya",
                "email": "",
                "phone": "",
                "tax_pin": "",
            },
            "invoice": {
                "number": "",
                "issue_date": datetime.now(timezone.utc).date().isoformat(),
                "currency": "USD",
                "incoterm": "CIF",
                "payment_status": "unpaid",
                "payment_reference": "",
            },
            "shipment": {
                "destination_country": "",
                "destination_port": "",
                "shipping_method": "",
                "export_reference": "",
            },
            "items": [
                {
                    "description": "Halal Meat",
                    "quantity_kg": 0,
                    "unit_price": 0,
                    "line_total": 0,
                }
            ],
            "totals": {
                "subtotal": 0,
                "tax": 0,
                "shipping": 0,
                "grand_total": 0,
            },
            "declaration": "",
            "notes": "",
        }
    },

    DOC_TYPE_PACKING_LIST: {
        "packing_list": {
            "buyer": {
                "name": "",
                "address": "",
                "country": "",
                "email": "",
                "phone": "",
            },
            "seller": {
                "name": "Rizara Meats Ltd",
                "address": "",
                "country": "Kenya",
            },
            "shipment": {
                "packing_list_number": "",
                "issue_date": datetime.now(timezone.utc).date().isoformat(),
                "destination_country": "",
                "destination_port": "",
                "shipping_method": "",
                "container_number": "",
                "seal_number": "",
            },
            "items": [
                {
                    "description": "Halal Meat",
                    "package_type": "",
                    "package_count": 0,
                    "net_weight_kg": 0,
                    "gross_weight_kg": 0,
                }
            ],
            "totals": {
                "total_packages": 0,
                "total_net_weight_kg": 0,
                "total_gross_weight_kg": 0,
            },
            "notes": "",
        }
    },
}

DEFAULT_TITLES = {
    DOC_TYPE_LOI: "Letter of Intent",
    DOC_TYPE_PROFORMA_INVOICE: "Proforma Invoice",
    DOC_TYPE_COMMERCIAL_INVOICE: "Commercial Invoice",
    DOC_TYPE_PACKING_LIST: "Packing List",
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

    Export sales contracts no longer start here.
    They belong to the Contracts module.
    """
    return "admin.documents_view"