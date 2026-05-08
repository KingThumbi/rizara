from __future__ import annotations

import secrets
from datetime import date, datetime
from typing import Iterable

from app.extensions import db
from app.models import AnimalEvent, utcnow_naive


def _normalize_animal_type(animal_type: str) -> str:
    normalized = (animal_type or "").strip().lower()
    if normalized not in {"goat", "sheep", "cattle"}:
        raise ValueError(f"Unsupported animal type: {animal_type}")
    return normalized


def _default_trace_code(animal, animal_type: str) -> str:
    existing_code = (getattr(animal, "rizara_id", None) or "").strip()
    if existing_code:
        return existing_code

    animal_id = getattr(animal, "id", None)
    if not animal_id:
        raise ValueError("Animal must have an id before trace identity can be generated.")

    return f"RZ-{animal_type.upper()}-{str(animal_id)[:8].upper()}"


def ensure_animal_trace_identity(animal, animal_type: str):
    """Mutating helper: populate trace fields on an animal object without committing."""
    normalized_type = _normalize_animal_type(animal_type)

    if not (getattr(animal, "trace_code", None) or "").strip():
        animal.trace_code = _default_trace_code(animal, normalized_type)

    if not (getattr(animal, "qr_code_token", None) or "").strip():
        animal.qr_code_token = secrets.token_urlsafe(24)

    return animal


def animal_qr_payload(animal, animal_type: str) -> dict[str, str | None]:
    """Read-only helper: return a route-independent QR payload for existing trace fields.

    This function intentionally does not generate missing trace fields. Call
    ensure_animal_trace_identity() first in a write workflow when identity
    creation is desired.
    """
    normalized_type = _normalize_animal_type(animal_type)

    token = getattr(animal, "qr_code_token", None)

    return {
        "payload_type": "animal_trace",
        "animal_type": normalized_type,
        "animal_id": str(getattr(animal, "id", "")),
        "trace_code": getattr(animal, "trace_code", None),
        "qr_code_token": token,
        "path": f"/trace/animal/{normalized_type}/{token}" if token else None,
    }


def record_traceability_event(
    *,
    animal,
    animal_type: str,
    event_type: str,
    event_datetime: datetime | None = None,
    event_date: date | None = None,
    source_module: str | None = None,
    reference_type: str | None = None,
    reference_id: int | None = None,
    notes: str | None = None,
    created_by_user_id: int | None = None,
    performed_by_user_id: int | None = None,
    from_farmer_id: int | None = None,
    to_farmer_id: int | None = None,
    from_location: str | None = None,
    to_location: str | None = None,
    session=None,
) -> AnimalEvent:
    """Mutating helper: add an AnimalEvent to the current transaction.

    The helper also ensures the animal has trace identity fields, but it does
    not commit. Callers own transaction boundaries.
    """
    normalized_type = _normalize_animal_type(animal_type)
    ensure_animal_trace_identity(animal, normalized_type)

    animal_id = getattr(animal, "id", None)
    if not animal_id:
        raise ValueError("Animal must have an id before traceability events can be recorded.")

    occurred_at = event_datetime or utcnow_naive()
    occurred_date = event_date or occurred_at.date()
    clean_event_type = (event_type or "").strip()

    if not clean_event_type:
        raise ValueError("event_type is required.")

    active_session = session or db.session

    if reference_type and reference_id is not None:
        with active_session.no_autoflush:
            existing_event = (
                active_session.query(AnimalEvent)
                .filter(
                    AnimalEvent.animal_type == normalized_type,
                    AnimalEvent.animal_id == animal_id,
                    AnimalEvent.event_type == clean_event_type,
                    AnimalEvent.reference_type == reference_type,
                    AnimalEvent.reference_id == reference_id,
                )
                .first()
            )
        if existing_event:
            return existing_event

    event = AnimalEvent(
        animal_type=normalized_type,
        animal_id=animal_id,
        event_type=clean_event_type,
        event_datetime=occurred_at,
        event_date=occurred_date,
        source_module=source_module,
        reference_type=reference_type,
        reference_id=reference_id,
        notes=notes,
        created_by_user_id=created_by_user_id,
        performed_by_user_id=performed_by_user_id or created_by_user_id,
        from_farmer_id=from_farmer_id,
        to_farmer_id=to_farmer_id,
        from_location=from_location,
        to_location=to_location,
    )

    active_session.add(event)
    return event


def record_events_for_animals(
    animals: Iterable,
    *,
    animal_type: str,
    event_type: str,
    event_datetime: datetime | None = None,
    event_date: date | None = None,
    source_module: str | None = None,
    reference_type: str | None = None,
    reference_id: int | None = None,
    notes: str | None = None,
    created_by_user_id: int | None = None,
    performed_by_user_id: int | None = None,
    session=None,
) -> list[AnimalEvent]:
    """Mutating helper: add one traceability event per animal without committing."""
    return [
        record_traceability_event(
            animal=animal,
            animal_type=animal_type,
            event_type=event_type,
            event_datetime=event_datetime,
            event_date=event_date,
            source_module=source_module,
            reference_type=reference_type,
            reference_id=reference_id,
            notes=notes,
            created_by_user_id=created_by_user_id,
            performed_by_user_id=performed_by_user_id,
            session=session,
        )
        for animal in animals
    ]
