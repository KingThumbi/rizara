from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

from flask import Flask
from flask_login import LoginManager
from werkzeug.security import generate_password_hash

from app.constants.impact_metrics import IMPACT_METRICS
from app.extensions import db
from app.models import (
    DonorOrganization,
    Farmer,
    FieldObservation,
    GrantApplication,
    GrantDocument,
    GrantImpactMetric,
    GrantMilestone,
    GrantOpportunity,
    GrantReport,
    Goat,
    ImpactSnapshot,
    InnovationProposal,
    MarketInsight,
    ProcurementRecord,
    ProcurementSource,
    ProjectDocument,
    ProjectMilestone,
    ProjectTask,
    ProjectWorkstream,
    ResearchDocument,
    ResearchProject,
    StrategicProject,
    TraceabilityRecord,
    User,
    AggregationBatch,
    EvidenceRecord,
)
from app.routes import institutional as institutional_routes
from app.routes.institutional import institutional_bp
from app.services.impact_metrics import calculate_impact_metrics, create_current_impact_snapshot
from app.services.reporting import assemble_grant_reporting_package


INSTITUTIONAL_TABLES = [
    User.__table__,
    Farmer.__table__,
    AggregationBatch.__table__,
    Goat.__table__,
    ProcurementSource.__table__,
    ProcurementRecord.__table__,
    TraceabilityRecord.__table__,
    EvidenceRecord.__table__,
    ResearchProject.__table__,
    FieldObservation.__table__,
    MarketInsight.__table__,
    InnovationProposal.__table__,
    ResearchDocument.__table__,
    DonorOrganization.__table__,
    GrantOpportunity.__table__,
    GrantApplication.__table__,
    GrantMilestone.__table__,
    GrantReport.__table__,
    GrantImpactMetric.__table__,
    GrantDocument.__table__,
    ImpactSnapshot.__table__,
    StrategicProject.__table__,
    ProjectWorkstream.__table__,
    ProjectMilestone.__table__,
    ProjectTask.__table__,
    ProjectDocument.__table__,
]


def make_institutional_app(monkeypatch, tmp_path: Path):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="test-secret",
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'institutional.sqlite'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    login_manager = LoginManager()
    login_manager.init_app(app)
    db.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.get("/admin/dashboard", endpoint="admin.dashboard")
    def admin_dashboard():
        return "admin dashboard"

    app.register_blueprint(institutional_bp)

    def fake_render_template(template, **context):
        labels = [template]
        for key in ("projects", "opportunities"):
            if key in context:
                labels.extend(item.title for item in context[key])
        if "applications" in context:
            labels.extend(item.title for item in context["applications"])
        for key in ("milestones", "documents"):
            if key in context:
                labels.extend(item.title for item in context[key])
        if "reports" in context:
            labels.extend(item.report_type for item in context["reports"])
        if "impact_metrics" in context:
            labels.extend(item.name for item in context["impact_metrics"])
        if "metrics" in context:
            labels.extend(item.definition.name for item in context["metrics"])
        if "recent_snapshots" in context:
            labels.extend(item.metric_name for item in context["recent_snapshots"])
        for key in ("project", "opportunity"):
            if key in context and getattr(context[key], "title", None):
                labels.append(context[key].title)
        if "application" in context and getattr(context["application"], "title", None):
            labels.append(context["application"].title)
        return "\n".join(labels)

    monkeypatch.setattr(institutional_routes, "render_template", fake_render_template)

    with app.app_context():
        db.metadata.create_all(db.engine, tables=INSTITUTIONAL_TABLES)
        admin = User(
            name="Admin User",
            email="admin@example.com",
            password_hash=generate_password_hash("CorrectPass123!"),
            role="admin",
            is_admin=True,
        )
        db.session.add(admin)
        db.session.commit()

    return app


def login_admin(client):
    with client.session_transaction() as session:
        session["_user_id"] = "1"
        session["_fresh"] = True


def test_institutional_routes_require_login(monkeypatch, tmp_path):
    app = make_institutional_app(monkeypatch, tmp_path)
    client = app.test_client()

    for path in ("/admin/research", "/admin/grants", "/admin/projects", "/admin/impact"):
        response = client.get(path)
        assert response.status_code in (302, 401)


def test_admin_pages_render_for_admin(monkeypatch, tmp_path):
    app = make_institutional_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    assert client.get("/admin/research").status_code == 200
    assert client.get("/admin/grants").status_code == 200
    assert client.get("/admin/projects").status_code == 200
    assert client.get("/admin/impact").status_code == 200


def test_research_create_list_flow(monkeypatch, tmp_path):
    app = make_institutional_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    response = client.post(
        "/admin/research/new",
        data={
            "title": "Goat Breed Yield Pilot",
            "code": "RD-001",
            "category": "breed_yield",
            "status": "active",
            "location": "Kajiado",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Goat Breed Yield Pilot" in response.get_data(as_text=True)
    assert "Goat Breed Yield Pilot" in client.get("/admin/research").get_data(as_text=True)


def test_grant_create_list_flow(monkeypatch, tmp_path):
    app = make_institutional_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    response = client.post(
        "/admin/grants/new",
        data={
            "title": "Livestock Climate Fund",
            "focus_area": "Climate resilient pastoral value chains",
            "status": "researching",
            "currency": "USD",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Livestock Climate Fund" in response.get_data(as_text=True)
    assert "Livestock Climate Fund" in client.get("/admin/grants").get_data(as_text=True)


def test_strategic_project_create_list_flow(monkeypatch, tmp_path):
    app = make_institutional_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    response = client.post(
        "/admin/projects/new",
        data={
            "title": "Export Readiness Pilot",
            "project_code": "SP-001",
            "category": "export_readiness",
            "status": "active",
            "priority": "high",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Export Readiness Pilot" in response.get_data(as_text=True)
    assert "Export Readiness Pilot" in client.get("/admin/projects").get_data(as_text=True)


def test_institutional_primary_records_get_uuids(monkeypatch, tmp_path):
    app = make_institutional_app(monkeypatch, tmp_path)

    with app.app_context():
        research = ResearchProject(title="Rangeland Intelligence")
        observation = FieldObservation(description="Forage condition note")
        insight = MarketInsight(title="GCC chilled goat demand")
        proposal = InnovationProposal(title="Cold-chain pilot")
        research_document = ResearchDocument(title="Observation protocol")
        donor = DonorOrganization(name="Example Foundation")
        opportunity = GrantOpportunity(title="Food Systems Fund")
        application = GrantApplication(title="Rizara Application", grant_opportunity=opportunity)
        milestone = GrantMilestone(title="Baseline due", grant_application=application)
        report = GrantReport(report_type="impact", grant_application=application)
        impact_metric = GrantImpactMetric(name="Pastoralist income lift", grant_application=application)
        grant_document = GrantDocument(title="Concept note", grant_application=application)
        project = StrategicProject(title="Traceability expansion")
        workstream = ProjectWorkstream(title="Technology", strategic_project=project)
        project_milestone = ProjectMilestone(title="Pilot launch", strategic_project=project)
        task = ProjectTask(title="Map users", strategic_project=project)
        project_document = ProjectDocument(title="Project charter", strategic_project=project)

        records = [
            research,
            observation,
            insight,
            proposal,
            research_document,
            donor,
            opportunity,
            application,
            milestone,
            report,
            impact_metric,
            grant_document,
            project,
            workstream,
            project_milestone,
            task,
            project_document,
        ]
        db.session.add_all(records)
        db.session.commit()

        for record in records:
            assert isinstance(record.uuid, uuid.UUID)


def test_archived_primary_records_are_hidden_from_default_lists(monkeypatch, tmp_path):
    app = make_institutional_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        db.session.add_all(
            [
                ResearchProject(title="Visible Research", is_archived=False),
                ResearchProject(title="Archived Research", is_archived=True),
                GrantOpportunity(title="Visible Grant", is_archived=False),
                GrantOpportunity(title="Archived Grant", is_archived=True),
                StrategicProject(title="Visible Project", is_archived=False),
                StrategicProject(title="Archived Project", is_archived=True),
            ]
        )
        db.session.commit()

    research = client.get("/admin/research").get_data(as_text=True)
    grants = client.get("/admin/grants").get_data(as_text=True)
    projects = client.get("/admin/projects").get_data(as_text=True)

    assert "Visible Research" in research
    assert "Archived Research" not in research
    assert "Visible Grant" in grants
    assert "Archived Grant" not in grants
    assert "Visible Project" in projects
    assert "Archived Project" not in projects


def test_grant_application_execution_flow(monkeypatch, tmp_path):
    app = make_institutional_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        opportunity = GrantOpportunity(title="Donor Livestock Resilience Fund")
        db.session.add(opportunity)
        db.session.commit()
        opportunity_id = opportunity.id

    response = client.post(
        "/admin/grants/applications/new",
        data={
            "grant_opportunity_id": str(opportunity_id),
            "title": "Rizara Livestock Intelligence Grant",
            "application_status": "submitted",
            "requested_amount": "250000",
            "currency": "USD",
            "project_title": "Livestock Intelligence and Export Readiness",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Rizara Livestock Intelligence Grant" in response.get_data(as_text=True)

    with app.app_context():
        application = GrantApplication.query.filter_by(title="Rizara Livestock Intelligence Grant").one()
        application_id = application.id
        assert application.uuid is not None

    for path, data, expected in (
        (
            f"/admin/grants/applications/{application_id}/milestones/new",
            {"title": "Baseline survey complete", "status": "pending", "due_date": "2026-06-30"},
            "Baseline survey complete",
        ),
        (
            f"/admin/grants/applications/{application_id}/reports/new",
            {"report_type": "impact", "status": "draft", "due_date": "2026-07-15", "summary": "Initial impact report"},
            "impact",
        ),
        (
            f"/admin/grants/applications/{application_id}/impact-metrics/new",
            {
                "name": "Herders reached",
                "metric_code": "pastoralists_onboarded",
                "metric_type": "output",
                "status": "in_progress",
                "target_value": "500",
                "current_value": "120",
                "unit": "people",
            },
            "Herders reached",
        ),
        (
            f"/admin/grants/applications/{application_id}/documents/new",
            {"title": "Submitted proposal", "document_type": "proposal", "external_url": "https://example.com/proposal"},
            "Submitted proposal",
        ),
    ):
        response = client.post(path, data=data, follow_redirects=True)
        assert response.status_code == 200
        assert expected in response.get_data(as_text=True)

    with app.app_context():
        assert GrantMilestone.query.filter_by(grant_application_id=application_id).count() == 1
        assert GrantReport.query.filter_by(grant_application_id=application_id).count() == 1
        assert GrantImpactMetric.query.filter_by(grant_application_id=application_id).count() == 1
        assert (
            GrantImpactMetric.query.filter_by(grant_application_id=application_id).one().metric_code
            == "pastoralists_onboarded"
        )
        assert GrantDocument.query.filter_by(grant_application_id=application_id).count() == 1


def test_grant_opportunity_document_registration(monkeypatch, tmp_path):
    app = make_institutional_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        opportunity = GrantOpportunity(title="Challenge Fund")
        db.session.add(opportunity)
        db.session.commit()
        opportunity_id = opportunity.id

    response = client.post(
        f"/admin/grants/{opportunity_id}/documents/new",
        data={
            "title": "Eligibility checklist",
            "document_type": "attachment",
            "external_url": "https://example.com/checklist",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Challenge Fund" in response.get_data(as_text=True)
    with app.app_context():
        document = GrantDocument.query.filter_by(grant_opportunity_id=opportunity_id).one()
        assert document.title == "Eligibility checklist"
        assert document.grant_application_id is None


def test_impact_metric_registry_consistency():
    expected_codes = {
        "pastoralists_onboarded",
        "animals_procured",
        "animals_aggregated",
        "animals_processed",
        "animals_traced",
        "traceability_coverage_percent",
        "active_grants",
        "awarded_grants",
        "overdue_reports",
        "active_projects",
        "invoices_generated",
        "total_sales_value",
        "goat_carcass_kg",
        "sheep_carcass_kg",
        "cattle_carcass_kg",
    }

    assert set(IMPACT_METRICS) == expected_codes
    for code, definition in IMPACT_METRICS.items():
        assert definition.code == code
        assert definition.name
        assert definition.category
        assert definition.source_module


def test_impact_metric_calculations_and_snapshot_creation(monkeypatch, tmp_path):
    app = make_institutional_app(monkeypatch, tmp_path)

    with app.app_context():
        farmer = Farmer(
            name="Pastoralist One",
            phone="0700000001",
            county="Kajiado",
            ward="Central",
        )
        source = ProcurementSource(source_type="farmer", name="Pastoralist One", county="Kajiado")
        opportunity = GrantOpportunity(title="Impact Grant")
        application = GrantApplication(
            title="Awarded Application",
            grant_opportunity=opportunity,
            application_status="awarded",
        )
        overdue_report = GrantReport(
            grant_application=application,
            report_type="impact",
            due_date=date(2026, 1, 1),
            status="draft",
        )
        project = StrategicProject(title="Active Impact Project", status="active")
        db.session.add_all([farmer, source, application, overdue_report, project])
        db.session.flush()

        goat = Goat(rizara_id="RZ-GOAT-IMPACT-001", farmer_id=farmer.id)
        procurement = ProcurementRecord(
            source_id=source.id,
            animal_type="goat",
            quantity=3,
            unit_price=100,
            total_cost=300,
            status="confirmed",
        )
        db.session.add_all([goat, procurement])
        db.session.flush()
        db.session.add(
            TraceabilityRecord(
                animal_type="goat",
                animal_id=goat.id,
                qr_code_data="trace-data",
                public_url="https://example.com/trace",
            )
        )
        db.session.commit()

        metrics = {metric.definition.code: metric.value for metric in calculate_impact_metrics()}
        assert metrics["pastoralists_onboarded"] == 1
        assert metrics["animals_procured"] == 3
        assert metrics["animals_traced"] == 1
        assert metrics["traceability_coverage_percent"] == 100
        assert metrics["active_grants"] == 1
        assert metrics["awarded_grants"] == 1
        assert metrics["overdue_reports"] == 1
        assert metrics["active_projects"] == 1

        snapshots = create_current_impact_snapshot(snapshot_date=date(2026, 5, 13))
        db.session.commit()
        assert len(snapshots) == len(IMPACT_METRICS)
        assert ImpactSnapshot.query.filter_by(metric_code="pastoralists_onboarded").one().metric_value == 1


def test_impact_dashboard_snapshot_action(monkeypatch, tmp_path):
    app = make_institutional_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    response = client.post("/admin/impact/snapshots/generate", follow_redirects=True)

    assert response.status_code == 200
    assert "Pastoralists Onboarded" in response.get_data(as_text=True)
    with app.app_context():
        assert ImpactSnapshot.query.count() == len(IMPACT_METRICS)


def test_snapshot_filtering_and_impact_csv_export(monkeypatch, tmp_path):
    app = make_institutional_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        db.session.add_all(
            [
                ImpactSnapshot(
                    snapshot_date=date(2026, 5, 1),
                    metric_code="animals_procured",
                    metric_name="Animals Procured",
                    metric_category="livestock_supply",
                    metric_value=12,
                    metric_unit="head",
                    county="Kajiado",
                    animal_type="goat",
                    source_module="procurement",
                ),
                ImpactSnapshot(
                    snapshot_date=date(2026, 5, 2),
                    metric_code="active_grants",
                    metric_name="Active Grants",
                    metric_category="institutional_grants",
                    metric_value=2,
                    metric_unit="applications",
                    source_module="grants",
                ),
            ]
        )
        db.session.commit()

    dashboard = client.get("/admin/impact?metric_category=livestock_supply").get_data(as_text=True)
    assert "Animals Procured" in dashboard

    export = client.get("/admin/impact/export.csv?metric_code=animals_procured")
    body = export.get_data(as_text=True)
    assert export.status_code == 200
    assert "metric_code,metric_name" in body
    assert "animals_procured" in body
    assert "active_grants" not in body


def test_evidence_creation_and_reporting_package(monkeypatch, tmp_path):
    app = make_institutional_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        opportunity = GrantOpportunity(title="Reporting Grant")
        application = GrantApplication(title="Reporting Application", grant_opportunity=opportunity)
        milestone = GrantMilestone(title="Training complete", grant_application=application)
        metric = GrantImpactMetric(
            name="Pastoralists onboarded",
            metric_code="pastoralists_onboarded",
            grant_application=application,
        )
        db.session.add_all([application, milestone, metric])
        db.session.flush()
        application_id = application.id
        milestone_id = milestone.id
        db.session.add(
            ImpactSnapshot(
                snapshot_date=date(2026, 5, 13),
                metric_code="pastoralists_onboarded",
                metric_name="Pastoralists Onboarded",
                metric_category="livestock_supply",
                metric_value=30,
                metric_unit="people",
                source_module="farmers",
            )
        )
        db.session.commit()

    response = client.post(
        f"/admin/evidence/new?next=/admin/grants/applications/{application_id}",
        data={
            "linked_model_type": "GrantMilestone",
            "linked_model_id": str(milestone_id),
            "title": "Attendance sheet",
            "evidence_type": "attendance",
            "external_url": "https://example.com/attendance",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        evidence = EvidenceRecord.query.filter_by(title="Attendance sheet").one()
        assert evidence.linked_model_type == "GrantMilestone"
        package = assemble_grant_reporting_package(application_id)
        assert package["summary"]["title"] == "Reporting Application"
        assert len(package["milestones"][0]["evidence"]) == 1
        linked_metric = package["impact_metrics"][0]["linked_operational_metric"]
        assert linked_metric["latest_value"] == 30


def test_grant_reporting_csv_export(monkeypatch, tmp_path):
    app = make_institutional_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        opportunity = GrantOpportunity(title="CSV Grant")
        application = GrantApplication(title="CSV Application", grant_opportunity=opportunity)
        db.session.add_all(
            [
                application,
                GrantMilestone(title="Submit baseline", grant_application=application),
                GrantReport(report_type="impact", grant_application=application, status="draft"),
                GrantImpactMetric(name="Animals procured", metric_code="animals_procured", grant_application=application),
            ]
        )
        db.session.commit()
        application_id = application.id

    response = client.get(f"/admin/grants/applications/{application_id}/report-export.csv")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "record_type,title,status" in body
    assert "Submit baseline" in body
    assert "impact_metric,Animals procured" in body


def test_institutional_migration_imports():
    migration = __import__(
        "migrations.versions.f4a9c2d7e8b1_add_institutional_foundation_tables",
        fromlist=["revision", "down_revision"],
    )
    impact_migration = __import__(
        "migrations.versions.0b8c6d4e2f31_add_grant_impact_metrics",
        fromlist=["revision", "down_revision"],
    )
    snapshot_migration = __import__(
        "migrations.versions.9d1e5f7a2c44_add_impact_snapshots",
        fromlist=["revision", "down_revision"],
    )
    evidence_migration = __import__(
        "migrations.versions.1a2b3c4d5e6f_add_evidence_records",
        fromlist=["revision", "down_revision"],
    )

    assert migration.revision == "f4a9c2d7e8b1"
    assert migration.down_revision == "d8f3b2a7c901"
    assert impact_migration.revision == "0b8c6d4e2f31"
    assert impact_migration.down_revision == "f4a9c2d7e8b1"
    assert snapshot_migration.revision == "9d1e5f7a2c44"
    assert snapshot_migration.down_revision == "0b8c6d4e2f31"
    assert evidence_migration.revision == "1a2b3c4d5e6f"
    assert evidence_migration.down_revision == "9d1e5f7a2c44"

    source = Path(migration.__file__).read_text()
    assert "export_compliance" in source
    assert "export', 'compliance" not in source
