from __future__ import annotations

import csv
import json
from io import BytesIO, StringIO
from datetime import date, datetime, timezone

import qrcode
from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    Response,
    send_file,
    url_for,
)
from flask_login import current_user

from app.extensions import db
from app.models import AnimalEvent
from app.services.traceability_service import (
    animal_qr_payload,
    ensure_animal_trace_identity,
    record_traceability_event,
)
from app.services.lineage_resolver import (
    find_animal_by_trace_token,
    get_animal_model,
    resolve_animal_lineage,
    summarize_lineage,
)
from app.utils.guards import admin_required


traceability_bp = Blueprint("traceability", __name__)
ANIMAL_TYPES = {"goat", "sheep", "cattle"}
BACKFILL_LIMIT = 500
EVENT_LIMIT_DEFAULT = 100
EVENT_LIMIT_MAX = 500
EVENT_CSV_COLUMNS = [
    "event_datetime",
    "event_date",
    "animal_type",
    "animal_id",
    "event_type",
    "source_module",
    "reference_type",
    "reference_id",
    "created_by_user_id",
    "created_at",
    "notes",
]
LIFECYCLE_EVENTS = [
    "procured",
    "aggregated",
    "moved_to_processing",
    "slaughtered_or_processed",
    "yield_recorded",
    "inventory_created",
    "invoiced_or_sold",
    "trace_identity_backfilled",
]


def _qr_payload_context(animal, animal_type: str, token: str):
    trace_code = getattr(animal, "trace_code", None)
    qr_token = getattr(animal, "qr_code_token", None)

    if not _has_trace_identity(animal):
        return {
            "trace_code": trace_code,
            "qr_code_token": qr_token,
            "qr_payload": None,
            "json_endpoint_url": None,
            "json_export_url": None,
            "qr_png_url": None,
        }

    payload = animal_qr_payload(animal, animal_type)
    json_token = payload.get("qr_code_token") or token

    return {
        "trace_code": trace_code,
        "qr_code_token": qr_token,
        "qr_payload": json.dumps(payload, sort_keys=True, default=str),
        "json_endpoint_url": url_for(
            "traceability.animal_lineage_json",
            animal_type=animal_type,
            token=json_token,
        ),
        "json_export_url": url_for(
            "traceability.animal_lineage_export_json",
            animal_type=animal_type,
            token=json_token,
        ),
        "qr_png_url": url_for(
            "traceability.animal_qr_png",
            animal_type=animal_type,
            token=json_token,
        ),
    }


def _has_trace_identity(animal) -> bool:
    return bool(
        (getattr(animal, "trace_code", None) or "").strip()
        and (getattr(animal, "qr_code_token", None) or "").strip()
    )


def _missing_trace_filter(Model):
    return (Model.trace_code.is_(None)) | (Model.qr_code_token.is_(None))


def _missing_fields(animal) -> list[str]:
    missing = []
    if not getattr(animal, "trace_code", None):
        missing.append("trace_code")
    if not getattr(animal, "qr_code_token", None):
        missing.append("qr_code_token")
    return missing


def _parse_iso_date(value: str | None):
    clean_value = (value or "").strip()
    if not clean_value:
        return None
    try:
        return date.fromisoformat(clean_value)
    except ValueError:
        return None


def _event_limit() -> int:
    try:
        requested_limit = int(request.args.get("limit", EVENT_LIMIT_DEFAULT))
    except (TypeError, ValueError):
        requested_limit = EVENT_LIMIT_DEFAULT

    return max(1, min(requested_limit, EVENT_LIMIT_MAX))


def _event_filter_values() -> dict[str, str]:
    return {
        "animal_type": (request.args.get("animal_type") or "all").strip().lower(),
        "event_type": (request.args.get("event_type") or "").strip(),
        "source_module": (request.args.get("source_module") or "").strip(),
        "date_from": (request.args.get("date_from") or "").strip(),
        "date_to": (request.args.get("date_to") or "").strip(),
    }


def _event_rows(events):
    return [
        {
            "event_datetime": getattr(event, "event_datetime", None),
            "event_date": getattr(event, "event_date", None),
            "animal_type": getattr(event, "animal_type", None),
            "animal_id": getattr(event, "animal_id", None),
            "event_type": getattr(event, "event_type", None),
            "source_module": getattr(event, "source_module", None),
            "reference_type": getattr(event, "reference_type", None),
            "reference_id": getattr(event, "reference_id", None),
            "created_by_user_id": getattr(event, "created_by_user_id", None),
            "created_at": getattr(event, "created_at", None),
            "notes": getattr(event, "notes", None),
        }
        for event in events
    ]


def _lineage_counts(lineage: dict) -> dict[str, int]:
    return {
        "processing_batches": len(lineage.get("processing_batches") or []),
        "inventory_lots": len(lineage.get("inventory_lots") or []),
        "invoice_items": len(lineage.get("invoice_items") or []),
        "invoices": len(lineage.get("invoices") or []),
        "events": len(lineage.get("events") or []),
    }


def _filtered_event_query(filters: dict[str, str]):
    query = AnimalEvent.query

    if filters["animal_type"] in ANIMAL_TYPES:
        query = query.filter(AnimalEvent.animal_type == filters["animal_type"])
    elif filters["animal_type"] != "all":
        filters["animal_type"] = "all"

    if filters["event_type"]:
        query = query.filter(AnimalEvent.event_type == filters["event_type"])

    if filters["source_module"]:
        query = query.filter(AnimalEvent.source_module == filters["source_module"])

    date_from = _parse_iso_date(filters["date_from"])
    if date_from:
        query = query.filter(AnimalEvent.event_date >= date_from)

    date_to = _parse_iso_date(filters["date_to"])
    if date_to:
        query = query.filter(AnimalEvent.event_date <= date_to)

    return query


def _limited_events(filters: dict[str, str], limit: int):
    return (
        _filtered_event_query(filters)
        .order_by(AnimalEvent.event_datetime.desc())
        .limit(limit)
        .all()
    )


def _csv_export_url(filters: dict[str, str], limit: int):
    query_args = {
        "animal_type": filters.get("animal_type") or "all",
        "limit": limit,
    }
    for key in ("event_type", "source_module", "date_from", "date_to"):
        if filters.get(key):
            query_args[key] = filters[key]

    return url_for("traceability.traceability_events_csv", **query_args)


def _event_coverage_counts() -> dict[tuple[str, str], int]:
    rows = (
        db.session
        .query(
            AnimalEvent.animal_type,
            AnimalEvent.event_type,
            db.func.count(db.func.distinct(AnimalEvent.animal_id)),
        )
        .filter(AnimalEvent.event_type.in_(LIFECYCLE_EVENTS))
        .group_by(AnimalEvent.animal_type, AnimalEvent.event_type)
        .all()
    )

    return {
        (animal_type, event_type): count
        for animal_type, event_type, count in rows
    }


def _trace_completeness_metrics():
    coverage_counts = _event_coverage_counts()
    metrics = []

    for animal_type in ("goat", "sheep", "cattle"):
        Model = get_animal_model(animal_type)
        metrics.append(
            {
                "animal_type": animal_type,
                "total_animals": Model.query.count(),
                "with_trace_code": Model.query.filter(Model.trace_code.isnot(None)).count(),
                "with_qr_code_token": Model.query.filter(Model.qr_code_token.isnot(None)).count(),
                "missing_either": Model.query.filter(_missing_trace_filter(Model)).count(),
                "event_coverage": {
                    event_type: coverage_counts.get((animal_type, event_type), 0)
                    for event_type in LIFECYCLE_EVENTS
                },
            }
        )

    return metrics


def _backfill_status_message():
    status = (request.args.get("backfill_status") or "").strip()
    count = request.args.get("backfill_count")

    if status == "dry_run":
        return (
            f"Dry run complete. {count or 0} animals would be updated, capped at {BACKFILL_LIMIT}.",
            "info",
        )
    if status == "missing_confirmation":
        return (
            "No trace identities were changed. Confirm the write action and clear dry-run before running the backfill.",
            "warning",
        )
    if status == "success":
        return (
            f"Trace identity backfill completed for {count or 0} animals.",
            "success",
        )
    if status == "error":
        return (
            "Trace identity backfill failed and was rolled back. Check application logs for details.",
            "danger",
        )

    return None, None


def _missing_identity_animals(limit: int = BACKFILL_LIMIT):
    selected = []

    for animal_type in ("goat", "sheep", "cattle"):
        remaining = limit - len(selected)
        if remaining <= 0:
            break

        Model = get_animal_model(animal_type)
        animals = (
            Model.query
            .filter(_missing_trace_filter(Model))
            .order_by(Model.created_at.asc())
            .limit(remaining)
            .all()
        )
        selected.extend((animal_type, animal) for animal in animals[:remaining])

    return selected


def _backfill_preview_for_type(animal_type: str, Model):
    sample_animals = (
        Model.query
        .filter(_missing_trace_filter(Model))
        .order_by(Model.created_at.desc())
        .limit(20)
        .all()
    )

    return {
        "animal_type": animal_type,
        "total_animals": Model.query.count(),
        "missing_trace_code": Model.query.filter(Model.trace_code.is_(None)).count(),
        "missing_qr_code_token": Model.query.filter(Model.qr_code_token.is_(None)).count(),
        "missing_either": Model.query.filter(_missing_trace_filter(Model)).count(),
        "sample": [
            {
                "animal_type": animal_type,
                "id": getattr(animal, "id", None),
                "rizara_id": getattr(animal, "rizara_id", None),
                "status": getattr(animal, "status", None),
                "source_type": getattr(animal, "source_type", None),
                "source_name": getattr(animal, "source_name", None),
                "aggregation_batch_id": getattr(animal, "aggregation_batch_id", None),
                "procurement_record_id": getattr(animal, "procurement_record_id", None),
                "missing_fields": _missing_fields(animal),
            }
            for animal in sample_animals
        ],
    }


@traceability_bp.get("/admin/traceability/backfill-preview")
@admin_required
def backfill_preview():
    backfill_message, backfill_message_category = _backfill_status_message()
    previews = [
        _backfill_preview_for_type(animal_type, get_animal_model(animal_type))
        for animal_type in ("goat", "sheep", "cattle")
    ]

    return render_template(
        "admin/traceability_backfill_preview.html",
        previews=previews,
        backfill_limit=BACKFILL_LIMIT,
        backfill_message=backfill_message,
        backfill_message_category=backfill_message_category,
        current_year=date.today().year,
    )


@traceability_bp.post("/admin/traceability/backfill-identities")
@admin_required
def backfill_identities():
    dry_run = request.form.get("dry_run") == "yes"
    confirmed = request.form.get("confirm_backfill") == "yes"
    selected_animals = _missing_identity_animals(BACKFILL_LIMIT)

    if dry_run:
        return redirect(
            url_for(
                "traceability.backfill_preview",
                backfill_status="dry_run",
                backfill_count=len(selected_animals),
            )
        )

    if not confirmed:
        return redirect(
            url_for(
                "traceability.backfill_preview",
                backfill_status="missing_confirmation",
                backfill_count=len(selected_animals),
            )
        )

    try:
        updated = 0
        for animal_type, animal in selected_animals:
            ensure_animal_trace_identity(animal, animal_type)

            animal_id = getattr(animal, "id", None)
            reference_id = animal_id if isinstance(animal_id, int) else None
            record_traceability_event(
                animal=animal,
                animal_type=animal_type,
                event_type="trace_identity_backfilled",
                source_module="traceability_admin",
                reference_type="animal",
                reference_id=reference_id,
                notes=f"Trace identity backfilled for animal {animal_id}.",
                created_by_user_id=getattr(current_user, "id", None),
            )
            updated += 1

        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Trace identity backfill failed")
        return redirect(url_for("traceability.backfill_preview", backfill_status="error"))

    return redirect(
        url_for(
            "traceability.backfill_preview",
            backfill_status="success",
            backfill_count=updated,
        )
    )


@traceability_bp.get("/admin/traceability/events")
@admin_required
def traceability_events():
    filters = _event_filter_values()
    limit = _event_limit()
    events = _limited_events(filters, limit)

    return render_template(
        "admin/traceability_events.html",
        events=_event_rows(events),
        filters=filters,
        limit=limit,
        csv_export_url=_csv_export_url(filters, limit),
        current_year=date.today().year,
    )


@traceability_bp.get("/admin/traceability/events.csv")
@admin_required
def traceability_events_csv():
    filters = _event_filter_values()
    events = _event_rows(_limited_events(filters, _event_limit()))

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=EVENT_CSV_COLUMNS)
    writer.writeheader()
    for event in events:
        writer.writerow({column: event.get(column) for column in EVENT_CSV_COLUMNS})

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=traceability-events.csv"},
    )


@traceability_bp.get("/admin/traceability/completeness")
@admin_required
def traceability_completeness():
    return render_template(
        "admin/traceability_completeness.html",
        metrics=_trace_completeness_metrics(),
        lifecycle_events=LIFECYCLE_EVENTS,
        current_year=date.today().year,
    )


@traceability_bp.get("/admin/traceability")
@admin_required
def traceability_lookup():
    animal_type = (request.args.get("animal_type") or "").strip().lower()
    token = (request.args.get("token") or "").strip()

    lineage = None
    summary = None
    qr_context = None
    message = None
    message_category = "info"

    if animal_type or token:
        if not token:
            message = "Token is required."
            message_category = "warning"
        elif animal_type not in ANIMAL_TYPES:
            message = "Animal type must be goat, sheep, or cattle."
            message_category = "danger"
        else:
            try:
                lineage = resolve_animal_lineage(animal_type, token)
            except ValueError:
                message = "Animal type must be goat, sheep, or cattle."
                message_category = "danger"
            else:
                if not lineage.get("animal"):
                    message = "No animal was found for that trace token."
                    message_category = "warning"
                else:
                    summary = summarize_lineage(lineage)
                    animal = lineage.get("animal")
                    qr_context = _qr_payload_context(animal, animal_type, token)

    return render_template(
        "admin/traceability_lookup.html",
        animal_type=animal_type,
        token=token,
        summary=summary,
        qr_context=qr_context,
        message=message,
        message_category=message_category,
        current_year=date.today().year,
    )


@traceability_bp.get("/admin/traceability/animal/<animal_type>/<token>/qr.png")
@admin_required
def animal_qr_png(animal_type: str, token: str):
    normalized_type = (animal_type or "").strip().lower()
    if normalized_type not in ANIMAL_TYPES:
        abort(400)

    animal = find_animal_by_trace_token(normalized_type, token)
    if not animal:
        abort(404)

    if not _has_trace_identity(animal):
        abort(422)

    payload = animal_qr_payload(animal, normalized_type)
    image = qrcode.make(json.dumps(payload, sort_keys=True, default=str))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="image/png",
        as_attachment=False,
        download_name=f"{normalized_type}-{getattr(animal, 'trace_code', 'trace')}.png",
        max_age=0,
    )


@traceability_bp.get("/admin/traceability/animal/<animal_type>/<token>.json")
@admin_required
def animal_lineage_json(animal_type: str, token: str):
    try:
        lineage = resolve_animal_lineage(animal_type, token)
    except ValueError:
        abort(400)

    if not lineage.get("animal"):
        abort(404)

    summary = summarize_lineage(lineage)

    return jsonify(
        {
            "ok": True,
            "animal_type": (animal_type or "").strip().lower(),
            "token": token,
            "summary": summary,
            "lineage_counts": _lineage_counts(lineage),
        }
    )


@traceability_bp.get("/admin/traceability/animal/<animal_type>/<token>/export.json")
@admin_required
def animal_lineage_export_json(animal_type: str, token: str):
    try:
        lineage = resolve_animal_lineage(animal_type, token)
    except ValueError:
        abort(400)

    if not lineage.get("animal"):
        abort(404)

    normalized_type = (animal_type or "").strip().lower()
    payload = {
        "animal_type": normalized_type,
        "token": token,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "summary": summarize_lineage(lineage),
        "lineage_counts": _lineage_counts(lineage),
    }

    return Response(
        json.dumps(payload, sort_keys=True, default=str),
        mimetype="application/json",
        headers={
            "Content-Disposition": (
                f"attachment; filename={normalized_type}-{token}-lineage.json"
            )
        },
    )
