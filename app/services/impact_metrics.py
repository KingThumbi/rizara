from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError

from app.constants.impact_metrics import IMPACT_METRICS, ImpactMetricDefinition
from app.extensions import db
from app.models import (
    AggregationBatch,
    Cattle,
    Farmer,
    Goat,
    GrantApplication,
    GrantReport,
    ImpactSnapshot,
    Invoice,
    InvoiceStatus,
    ProcessingBatch,
    ProcessingYield,
    ProcurementRecord,
    Sheep,
    StrategicProject,
    TraceabilityRecord,
    processing_cattle,
    processing_goats,
    processing_sheep,
)


@dataclass(frozen=True)
class CalculatedImpactMetric:
    definition: ImpactMetricDefinition
    value: Decimal
    county: str | None = None
    animal_type: str | None = None
    notes: str | None = None


def _decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _count(query) -> Decimal:
    try:
        return _decimal(query.scalar() or 0)
    except SQLAlchemyError:
        db.session.rollback()
        return Decimal("0")


def _sum(query) -> Decimal:
    try:
        return _decimal(query.scalar() or 0)
    except SQLAlchemyError:
        db.session.rollback()
        return Decimal("0")


def _animal_total() -> Decimal:
    return _count(db.session.query(sa.func.count(Goat.id))) + _count(
        db.session.query(sa.func.count(Sheep.id))
    ) + _count(db.session.query(sa.func.count(Cattle.id)))


def _animals_aggregated() -> Decimal:
    return _sum(
        db.session.query(sa.func.coalesce(sa.func.sum(ProcurementRecord.quantity), 0)).filter(
            ProcurementRecord.status != "cancelled"
        )
    ) + _count(db.session.query(sa.func.count(Goat.id)).filter(Goat.aggregation_batch_id.isnot(None))) + _count(
        db.session.query(sa.func.count(Sheep.id)).filter(Sheep.aggregation_batch_id.isnot(None))
    ) + _count(db.session.query(sa.func.count(Cattle.id)).filter(Cattle.aggregation_batch_id.isnot(None)))


def _animals_processed() -> Decimal:
    return _count(db.session.query(sa.func.count(processing_goats.c.goat_id))) + _count(
        db.session.query(sa.func.count(processing_sheep.c.sheep_id))
    ) + _count(db.session.query(sa.func.count(processing_cattle.c.cattle_id)))


def _carcass_kg(animal_type: str) -> Decimal:
    return _sum(
        db.session.query(sa.func.coalesce(sa.func.sum(ProcessingYield.total_carcass_weight_kg), 0))
        .join(ProcessingBatch, ProcessingYield.processing_batch_id == ProcessingBatch.id)
        .filter(ProcessingBatch.animal_type == animal_type)
    )


def calculate_impact_metrics() -> list[CalculatedImpactMetric]:
    total_animals = _animal_total()
    traced_animals = _count(db.session.query(sa.func.count(sa.distinct(TraceabilityRecord.animal_id))))
    coverage = Decimal("0")
    if total_animals:
        coverage = (traced_animals / total_animals * Decimal("100")).quantize(Decimal("0.01"))

    values: dict[str, Decimal] = {
        "pastoralists_onboarded": _count(db.session.query(sa.func.count(Farmer.id))),
        "animals_procured": _sum(
            db.session.query(sa.func.coalesce(sa.func.sum(ProcurementRecord.quantity), 0)).filter(
                ProcurementRecord.status != "cancelled"
            )
        ),
        "animals_aggregated": _animals_aggregated(),
        "animals_processed": _animals_processed(),
        "animals_traced": traced_animals,
        "traceability_coverage_percent": coverage,
        "active_grants": _count(
            db.session.query(sa.func.count(GrantApplication.id)).filter(
                GrantApplication.is_archived.is_(False),
                GrantApplication.application_status.in_(
                    ["drafting", "submitted", "under_review", "shortlisted", "awarded"]
                ),
            )
        ),
        "awarded_grants": _count(
            db.session.query(sa.func.count(GrantApplication.id)).filter(
                GrantApplication.is_archived.is_(False),
                GrantApplication.application_status == "awarded",
            )
        ),
        "overdue_reports": _count(
            db.session.query(sa.func.count(GrantReport.id)).filter(
                GrantReport.due_date.isnot(None),
                GrantReport.due_date < date.today(),
                GrantReport.status.notin_(["submitted", "accepted"]),
            )
        ),
        "active_projects": _count(
            db.session.query(sa.func.count(StrategicProject.id)).filter(
                StrategicProject.is_archived.is_(False),
                StrategicProject.status == "active",
            )
        ),
        "invoices_generated": _count(db.session.query(sa.func.count(Invoice.id))),
        "total_sales_value": _sum(
            db.session.query(sa.func.coalesce(sa.func.sum(Invoice.total), 0)).filter(
                Invoice.status != InvoiceStatus.VOID
            )
        ),
        "goat_carcass_kg": _carcass_kg("goat"),
        "sheep_carcass_kg": _carcass_kg("sheep"),
        "cattle_carcass_kg": _carcass_kg("cattle"),
    }

    return [
        CalculatedImpactMetric(definition=IMPACT_METRICS[code], value=value)
        for code, value in values.items()
    ]


def group_metrics(metrics: list[CalculatedImpactMetric]) -> dict[str, list[CalculatedImpactMetric]]:
    grouped: dict[str, list[CalculatedImpactMetric]] = {}
    for metric in metrics:
        grouped.setdefault(metric.definition.category, []).append(metric)
    return grouped


def create_current_impact_snapshot(snapshot_date: date | None = None) -> list[ImpactSnapshot]:
    snapshot_date = snapshot_date or date.today()
    snapshots: list[ImpactSnapshot] = []
    for metric in calculate_impact_metrics():
        snapshot = ImpactSnapshot(
            snapshot_date=snapshot_date,
            metric_code=metric.definition.code,
            metric_name=metric.definition.name,
            metric_category=metric.definition.category,
            metric_value=metric.value,
            metric_unit=metric.definition.unit,
            county=metric.county,
            animal_type=metric.animal_type,
            source_module=metric.definition.source_module,
            notes=metric.notes or metric.definition.description,
        )
        db.session.add(snapshot)
        snapshots.append(snapshot)
    return snapshots
