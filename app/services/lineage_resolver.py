from __future__ import annotations

import uuid
from typing import Any

from app.models import (
    AnimalEvent,
    Cattle,
    Goat,
    InventoryLot,
    Invoice,
    InvoiceItem,
    ProcessingBatch,
    Sheep,
)


ANIMAL_MODELS = {
    "goat": Goat,
    "sheep": Sheep,
    "cattle": Cattle,
}


def _normalize_animal_type(animal_type: str) -> str:
    normalized = (animal_type or "").strip().lower()
    if normalized not in ANIMAL_MODELS:
        raise ValueError(f"Unsupported animal type: {animal_type}")
    return normalized


def _as_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _scalar_identity(obj) -> dict[str, Any] | None:
    if obj is None:
        return None

    return {
        "id": getattr(obj, "id", None),
        "label": (
            getattr(obj, "rizara_id", None)
            or getattr(obj, "batch_number", None)
            or getattr(obj, "invoice_number", None)
            or getattr(obj, "name", None)
            or str(getattr(obj, "id", ""))
        ),
    }


def _processing_batches_for_animal(animal, animal_type: str) -> list[ProcessingBatch]:
    relationship_name = {
        "goat": "goats",
        "sheep": "sheep",
        "cattle": "cattle",
    }[animal_type]

    animal_batches = getattr(animal, "processing_batches", None)
    if animal_batches is not None:
        return list(animal_batches or [])

    return (
        ProcessingBatch.query
        .filter(getattr(ProcessingBatch, relationship_name).contains(animal))
        .order_by(ProcessingBatch.created_at.asc(), ProcessingBatch.id.asc())
        .all()
    )


def get_animal_model(animal_type):
    """Read-only helper: return the concrete animal model for a supported type."""
    return ANIMAL_MODELS[_normalize_animal_type(animal_type)]


def find_animal_by_trace_token(animal_type, token):
    """Read-only helper: find one animal by QR token, UUID, trace code, or Rizara ID."""
    normalized_type = _normalize_animal_type(animal_type)
    Model = get_animal_model(normalized_type)
    clean_token = (str(token or "")).strip()

    if not clean_token:
        return None

    animal = Model.query.filter(Model.qr_code_token == clean_token).first()
    if animal:
        return animal

    animal_uuid = _as_uuid(clean_token)
    if animal_uuid:
        animal = Model.query.get(animal_uuid)
        if animal:
            return animal

    return (
        Model.query
        .filter(
            (Model.trace_code == clean_token)
            | (Model.rizara_id == clean_token)
        )
        .first()
    )


def resolve_animal_lineage(animal_type, animal_id_or_token):
    """Read-only resolver for one animal's procurement-to-commercial lineage."""
    normalized_type = _normalize_animal_type(animal_type)
    animal = find_animal_by_trace_token(normalized_type, animal_id_or_token)

    if not animal:
        return {
            "animal": None,
            "trace_identity": None,
            "procurement_record": None,
            "farmer": None,
            "aggregation_batch": None,
            "processing_batches": [],
            "inventory_lots": [],
            "invoice_items": [],
            "invoices": [],
            "events": [],
        }

    procurement_record = getattr(animal, "procurement_record", None)
    farmer = getattr(animal, "farmer", None)
    aggregation_batch = getattr(animal, "aggregation_batch", None)
    processing_batches = _processing_batches_for_animal(animal, normalized_type)
    processing_batch_ids = [batch.id for batch in processing_batches if batch.id is not None]

    inventory_lots = []
    if processing_batch_ids:
        inventory_lots = (
            InventoryLot.query
            .filter(InventoryLot.processing_batch_id.in_(processing_batch_ids))
            .order_by(InventoryLot.created_at.asc(), InventoryLot.id.asc())
            .all()
        )

    inventory_lot_ids = [lot.id for lot in inventory_lots if lot.id is not None]

    invoice_items = []
    if inventory_lot_ids:
        invoice_items = (
            InvoiceItem.query
            .filter(InvoiceItem.inventory_lot_id.in_(inventory_lot_ids))
            .order_by(InvoiceItem.id.asc())
            .all()
        )

    invoice_ids = sorted(
        {
            item.invoice_id
            for item in invoice_items
            if getattr(item, "invoice_id", None) is not None
        }
    )

    invoices = []
    if invoice_ids:
        invoices = (
            Invoice.query
            .filter(Invoice.id.in_(invoice_ids))
            .order_by(Invoice.issue_date.asc(), Invoice.id.asc())
            .all()
        )

    events = (
        AnimalEvent.query
        .filter(
            AnimalEvent.animal_type == normalized_type,
            AnimalEvent.animal_id == animal.id,
        )
        .order_by(AnimalEvent.event_datetime.asc(), AnimalEvent.id.asc())
        .all()
    )

    return {
        "animal": animal,
        "trace_identity": {
            "animal_type": normalized_type,
            "animal_id": animal.id,
            "rizara_id": getattr(animal, "rizara_id", None),
            "trace_code": getattr(animal, "trace_code", None),
            "qr_code_token": getattr(animal, "qr_code_token", None),
            "status": getattr(animal, "status", None),
        },
        "procurement_record": procurement_record,
        "farmer": farmer,
        "aggregation_batch": aggregation_batch,
        "processing_batches": processing_batches,
        "inventory_lots": inventory_lots,
        "invoice_items": invoice_items,
        "invoices": invoices,
        "events": events,
    }


def summarize_lineage(lineage):
    """Read-only formatter for compact export/admin lineage summaries."""
    trace_identity = lineage.get("trace_identity") or {}
    animal = lineage.get("animal")
    procurement_record = lineage.get("procurement_record")
    farmer = lineage.get("farmer")
    aggregation_batch = lineage.get("aggregation_batch")
    processing_batches = lineage.get("processing_batches") or []
    inventory_lots = lineage.get("inventory_lots") or []
    invoice_items = lineage.get("invoice_items") or []
    invoices = lineage.get("invoices") or []
    events = lineage.get("events") or []

    return {
        "identity": {
            **trace_identity,
            "farmer_tag": getattr(animal, "farmer_tag", None) if animal else None,
        },
        "origin": {
            "farmer": _scalar_identity(farmer),
            "procurement_record": _scalar_identity(procurement_record),
            "source_type": getattr(animal, "source_type", None) if animal else None,
            "source_name": getattr(animal, "source_name", None) if animal else None,
        },
        "aggregation": {
            "batch": _scalar_identity(aggregation_batch),
            "site_name": getattr(aggregation_batch, "site_name", None),
            "date_received": getattr(aggregation_batch, "date_received", None),
        },
        "processing": [
            {
                "id": batch.id,
                "facility": batch.facility,
                "slaughter_date": batch.slaughter_date,
                "halal_cert_ref": batch.halal_cert_ref,
            }
            for batch in processing_batches
        ],
        "inventory": [
            {
                "id": lot.id,
                "batch_number": lot.batch_number,
                "product_name": lot.product_name,
                "quantity_kg": lot.quantity_kg,
                "available_kg": lot.available_kg,
                "status": lot.status,
            }
            for lot in inventory_lots
        ],
        "commercial": {
            "invoice_items": [
                {
                    "id": item.id,
                    "invoice_id": item.invoice_id,
                    "inventory_lot_id": item.inventory_lot_id,
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit": item.unit,
                }
                for item in invoice_items
            ],
            "invoices": [
                {
                    "id": invoice.id,
                    "invoice_number": invoice.invoice_number,
                    "issue_date": invoice.issue_date,
                    "status": getattr(invoice.status, "value", invoice.status),
                    "total": invoice.total,
                    "currency": invoice.currency,
                }
                for invoice in invoices
            ],
        },
        "audit_trail": [
            {
                "id": event.id,
                "event_type": event.event_type,
                "event_date": event.event_date,
                "event_datetime": event.event_datetime,
                "source_module": event.source_module,
                "reference_type": event.reference_type,
                "reference_id": event.reference_id,
                "notes": event.notes,
            }
            for event in events
        ],
    }
