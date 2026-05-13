from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.constants.impact_metrics import IMPACT_METRICS
from app.models import (
    EvidenceRecord,
    GrantApplication,
    GrantImpactMetric,
    GrantMilestone,
    GrantReport,
    ImpactSnapshot,
)


def _metric_snapshot_summary(metric_code: str | None) -> dict | None:
    if not metric_code:
        return None
    latest = ImpactSnapshot.query.filter_by(metric_code=metric_code).order_by(
        ImpactSnapshot.snapshot_date.desc(),
        ImpactSnapshot.created_at.desc(),
    ).first()
    definition = IMPACT_METRICS.get(metric_code)
    return {
        "metric_code": metric_code,
        "metric_name": definition.name if definition else metric_code,
        "latest_value": latest.metric_value if latest else None,
        "latest_date": latest.snapshot_date if latest else None,
        "unit": latest.metric_unit if latest else (definition.unit if definition else None),
    }


def assemble_grant_reporting_package(application_id: int) -> dict:
    application = GrantApplication.query.get_or_404(application_id)
    milestones = GrantMilestone.query.filter_by(grant_application_id=application.id).order_by(
        GrantMilestone.due_date.asc().nullslast(),
        GrantMilestone.created_at.desc(),
    ).all()
    reports = GrantReport.query.filter_by(grant_application_id=application.id).order_by(
        GrantReport.due_date.asc().nullslast(),
        GrantReport.created_at.desc(),
    ).all()
    impact_metrics = GrantImpactMetric.query.filter_by(grant_application_id=application.id).order_by(
        GrantImpactMetric.created_at.desc()
    ).all()

    linked_evidence = EvidenceRecord.query.filter(
        EvidenceRecord.linked_model_type.in_(["GrantReport", "GrantMilestone", "GrantImpactMetric"]),
    ).all()
    evidence_by_key: dict[tuple[str, int], list[EvidenceRecord]] = {}
    for record in linked_evidence:
        evidence_by_key.setdefault((record.linked_model_type, record.linked_model_id), []).append(record)

    return {
        "application": application,
        "opportunity": application.grant_opportunity,
        "summary": {
            "title": application.title,
            "status": application.application_status,
            "requested_amount": application.requested_amount,
            "awarded_amount": application.awarded_amount,
            "currency": application.currency,
            "submission_date": application.submission_date,
        },
        "milestones": [
            {
                "record": milestone,
                "evidence": evidence_by_key.get(("GrantMilestone", milestone.id), []),
            }
            for milestone in milestones
        ],
        "reports": [
            {
                "record": report,
                "evidence": evidence_by_key.get(("GrantReport", report.id), []),
            }
            for report in reports
        ],
        "impact_metrics": [
            {
                "record": metric,
                "linked_operational_metric": _metric_snapshot_summary(metric.metric_code),
                "evidence": evidence_by_key.get(("GrantImpactMetric", metric.id), []),
            }
            for metric in impact_metrics
        ],
    }


def grant_reporting_export_rows(application_id: int) -> list[dict]:
    package = assemble_grant_reporting_package(application_id)
    rows: list[dict] = []
    application = package["application"]

    for item in package["milestones"]:
        milestone = item["record"]
        rows.append(
            {
                "record_type": "milestone",
                "title": milestone.title,
                "status": milestone.status,
                "due_date": milestone.due_date,
                "submitted_or_completed_date": None,
                "metric_code": None,
                "value": None,
                "unit": None,
                "evidence_count": len(item["evidence"]),
                "application": application.title,
            }
        )

    for item in package["reports"]:
        report = item["record"]
        rows.append(
            {
                "record_type": "report",
                "title": report.report_type,
                "status": report.status,
                "due_date": report.due_date,
                "submitted_or_completed_date": report.submitted_date,
                "metric_code": None,
                "value": None,
                "unit": None,
                "evidence_count": len(item["evidence"]),
                "application": application.title,
            }
        )

    for item in package["impact_metrics"]:
        metric = item["record"]
        operational = item["linked_operational_metric"] or {}
        value = metric.current_value
        if value is None and operational.get("latest_value") is not None:
            value = operational["latest_value"]
        rows.append(
            {
                "record_type": "impact_metric",
                "title": metric.name,
                "status": metric.status,
                "due_date": metric.reporting_period_end,
                "submitted_or_completed_date": None,
                "metric_code": metric.metric_code,
                "value": value,
                "unit": metric.unit or operational.get("unit"),
                "evidence_count": len(item["evidence"]),
                "application": application.title,
            }
        )

    return rows
