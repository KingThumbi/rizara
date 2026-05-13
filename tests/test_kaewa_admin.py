from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from flask import Flask
from flask_login import LoginManager
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import (
    AggregationBatch,
    Cattle,
    Farmer,
    FieldLivestockIntake,
    FieldLivestockIntakeActivity,
    Goat,
    HoldingPen,
    HoldingPenActivity,
    HoldingPenAssignment,
    ProcurementRecord,
    ProcurementSource,
    Sheep,
    Stakeholder,
    StakeholderActivity,
    StakeholderDocument,
    User,
)
from app.routes import kaewa as kaewa_routes
from app.routes.kaewa import kaewa_bp


KAEWA_TABLES = [
    User.__table__,
    Farmer.__table__,
    AggregationBatch.__table__,
    ProcurementSource.__table__,
    ProcurementRecord.__table__,
    Stakeholder.__table__,
    StakeholderActivity.__table__,
    StakeholderDocument.__table__,
    FieldLivestockIntake.__table__,
    FieldLivestockIntakeActivity.__table__,
    HoldingPen.__table__,
    HoldingPenAssignment.__table__,
    HoldingPenActivity.__table__,
]


def make_kaewa_app(monkeypatch, tmp_path: Path):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="test-secret",
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'kaewa.sqlite'}",
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

    app.register_blueprint(kaewa_bp)

    def fake_render_template(template, **context):
        labels = [template]
        if "stats" in context:
            labels.extend(str(value) for value in context["stats"].values())
        for key in (
            "stakeholders",
            "activities",
            "documents",
            "intakes",
            "recent_activities",
            "recent_intakes",
            "active_assignments",
            "released_assignments",
        ):
            for item in context.get(key, []):
                for attr in ("name", "subject", "title", "animal_type", "source_location", "intake_status", "status"):
                    value = getattr(item, attr, None)
                    if value:
                        labels.append(str(value))
                if getattr(item, "count", None) is not None:
                    labels.append(str(item.count))
        for key in ("pen_summaries", "holding_pen_summaries"):
            for summary in context.get(key, []):
                pen = summary["pen"]
                labels.extend([pen.name, str(summary["occupancy"])])
        if "aggregation_batches" in context:
            labels.extend(batch.site_name for batch in context["aggregation_batches"])
        if "handoff_events" in context:
            labels.extend(event.event_type for event in context["handoff_events"])
        for key in ("stakeholder", "intake", "pen"):
            item = context.get(key)
            if item is not None:
                for attr in (
                    "name",
                    "phone",
                    "category",
                    "animal_type",
                    "source_location",
                    "intake_status",
                    "handoff_status",
                    "status",
                ):
                    value = getattr(item, attr, None)
                    if value:
                        labels.append(str(value))
        return "\n".join(labels)

    monkeypatch.setattr(kaewa_routes, "render_template", fake_render_template)

    with app.app_context():
        db.metadata.create_all(db.engine, tables=KAEWA_TABLES)
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


def assert_animal_tables_not_created(engine):
    inspector = sa.inspect(engine)
    assert not inspector.has_table(Goat.__tablename__)
    assert not inspector.has_table(Sheep.__tablename__)
    assert not inspector.has_table(Cattle.__tablename__)


def test_kaewa_routes_require_login(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()

    for path in ("/admin/kaewa", "/admin/kaewa/stakeholders", "/admin/kaewa/intakes", "/admin/kaewa/holding-pens"):
        response = client.get(path)
        assert response.status_code in (302, 401)

    for path in (
        "/admin/kaewa/intakes/1/handoff/ready",
        "/admin/kaewa/intakes/1/handoff/link-batch",
        "/admin/kaewa/holding-pens/1/assign",
        "/admin/kaewa/holding-assignments/1/release",
    ):
        response = client.post(path)
        assert response.status_code in (302, 401)


def test_kaewa_dashboard_loads_for_admin(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    response = client.get("/admin/kaewa")

    assert response.status_code == 200
    assert "admin/kaewa/dashboard.html" in response.get_data(as_text=True)


def test_stakeholder_creation_and_filtering(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    response = client.post(
        "/admin/kaewa/stakeholders/new",
        data={
            "name": "Kaewa Pastoralist One",
            "phone": "0711000001",
            "email": "pastoralist@example.com",
            "category": "farmer",
            "county": "Machakos",
            "sub_county": "Yatta",
            "ward": "Kaewa",
            "village": "Kithimani",
            "status": "active",
            "notes": "Interested in aggregation pilot.",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Kaewa Pastoralist One" in response.get_data(as_text=True)

    filtered = client.get("/admin/kaewa/stakeholders?category=farmer&status=active&county=Machakos")
    body = filtered.get_data(as_text=True)
    assert filtered.status_code == 200
    assert "Kaewa Pastoralist One" in body

    with app.app_context():
        stakeholder = Stakeholder.query.filter_by(name="Kaewa Pastoralist One").one()
        assert stakeholder.uuid is not None
        assert stakeholder.created_by_user_id == 1


def test_stakeholder_activity_creation(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        stakeholder = Stakeholder(name="Kaewa Vet", phone="0711000002", category="vet")
        db.session.add(stakeholder)
        db.session.commit()
        stakeholder_id = stakeholder.id

    response = client.post(
        f"/admin/kaewa/stakeholders/{stakeholder_id}/activities/new",
        data={
            "activity_type": "liaison",
            "subject": "Introductory field visit",
            "activity_date": "2026-05-13",
            "notes": "Discussed verification support.",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Introductory field visit" in response.get_data(as_text=True)
    with app.app_context():
        assert StakeholderActivity.query.filter_by(stakeholder_id=stakeholder_id).count() == 1


def test_intake_creation_and_status_update_without_animals(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        stakeholder = Stakeholder(name="Aggregation Agent", phone="0711000003", category="aggregation_agent")
        db.session.add(stakeholder)
        db.session.commit()
        stakeholder_id = stakeholder.id
        assert_animal_tables_not_created(db.engine)

    response = client.post(
        "/admin/kaewa/intakes/new",
        data={
            "stakeholder_id": str(stakeholder_id),
            "office_location": "Kaewa",
            "animal_type": "goat",
            "count": "12",
            "estimated_total_weight_kg": "360",
            "source_location": "Kaewa Ward",
            "intake_status": "pending_verification",
            "notes": "Awaiting field verification.",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "goat" in response.get_data(as_text=True)

    with app.app_context():
        intake = FieldLivestockIntake.query.one()
        intake_id = intake.id
        assert intake.uuid is not None
        assert intake.stakeholder_id == stakeholder_id
        assert intake.handoff_status == "none"
        assert_animal_tables_not_created(db.engine)

    response = client.post(
        f"/admin/kaewa/intakes/{intake_id}/status",
        data={"intake_status": "accepted"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        intake = db.session.get(FieldLivestockIntake, intake_id)
        assert intake.intake_status == "accepted"
        assert_animal_tables_not_created(db.engine)


def test_draft_intake_cannot_be_handed_off(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        intake = FieldLivestockIntake(
            animal_type="goat",
            count=5,
            intake_status="draft",
            source_location="Kaewa Ward",
        )
        db.session.add(intake)
        db.session.commit()
        intake_id = intake.id

    response = client.post(
        f"/admin/kaewa/intakes/{intake_id}/handoff/ready",
        data={"handoff_notes": "Premature review"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        intake = db.session.get(FieldLivestockIntake, intake_id)
        assert intake.handoff_status == "none"
        assert intake.reviewed_by_user_id is None
        assert FieldLivestockIntakeActivity.query.filter_by(intake_id=intake_id).count() == 0


def test_accepted_intake_can_be_marked_ready(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        intake = FieldLivestockIntake(
            animal_type="sheep",
            count=8,
            intake_status="accepted",
            source_location="Kaewa Ward",
        )
        db.session.add(intake)
        db.session.commit()
        intake_id = intake.id

    response = client.post(
        f"/admin/kaewa/intakes/{intake_id}/handoff/ready",
        data={"handoff_notes": "Verified by field office."},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "ready_for_aggregation" in response.get_data(as_text=True)
    with app.app_context():
        intake = db.session.get(FieldLivestockIntake, intake_id)
        assert intake.handoff_status == "ready_for_aggregation"
        assert intake.reviewed_by_user_id == 1
        assert intake.reviewed_at is not None
        event = FieldLivestockIntakeActivity.query.filter_by(intake_id=intake_id).one()
        assert event.from_status == "none"
        assert event.to_status == "ready_for_aggregation"


def test_ready_intake_can_link_to_existing_aggregation_batch_without_animals(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        batch = AggregationBatch(
            animal_type="goat",
            site_name="Kaewa Aggregation Yard",
            created_by_user_id=1,
        )
        intake = FieldLivestockIntake(
            animal_type="goat",
            count=12,
            intake_status="accepted",
            handoff_status="ready_for_aggregation",
            source_location="Kaewa Ward",
        )
        db.session.add_all([batch, intake])
        db.session.commit()
        batch_id = batch.id
        intake_id = intake.id
        assert_animal_tables_not_created(db.engine)

    response = client.post(
        f"/admin/kaewa/intakes/{intake_id}/handoff/link-batch",
        data={
            "aggregation_batch_id": str(batch_id),
            "handoff_notes": "Linked after office review.",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "handed_off" in response.get_data(as_text=True)
    with app.app_context():
        intake = db.session.get(FieldLivestockIntake, intake_id)
        assert intake.linked_aggregation_batch_id == batch_id
        assert intake.handoff_status == "handed_off"
        assert intake.intake_status == "transferred_to_aggregation"
        event = FieldLivestockIntakeActivity.query.filter_by(intake_id=intake_id).one()
        assert event.to_status == "handed_off"
        assert_animal_tables_not_created(db.engine)


def test_create_holding_pen(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    response = client.post(
        "/admin/kaewa/holding-pens/new",
        data={
            "name": "Kaewa Goat Pen A",
            "office_location": "Kaewa",
            "animal_type": "goat",
            "capacity_count": "20",
            "status": "active",
            "notes": "Near office yard.",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Kaewa Goat Pen A" in response.get_data(as_text=True)
    with app.app_context():
        pen = HoldingPen.query.filter_by(name="Kaewa Goat Pen A").one()
        assert pen.uuid is not None
        assert pen.capacity_count == 20


def test_assign_intake_to_active_holding_pen(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        pen = HoldingPen(name="Kaewa Mixed Pen", animal_type="mixed", capacity_count=20, status="active")
        intake = FieldLivestockIntake(
            animal_type="goat",
            count=12,
            estimated_total_weight_kg=360,
            intake_status="accepted",
            source_location="Kaewa Ward",
        )
        db.session.add_all([pen, intake])
        db.session.commit()
        pen_id = pen.id
        intake_id = intake.id
        assert_animal_tables_not_created(db.engine)

    response = client.post(
        f"/admin/kaewa/holding-pens/{pen_id}/assign",
        data={
            "field_livestock_intake_id": str(intake_id),
            "notes": "Holding before market-day aggregation.",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Kaewa Mixed Pen" in response.get_data(as_text=True)
    with app.app_context():
        assignment = HoldingPenAssignment.query.filter_by(holding_pen_id=pen_id).one()
        assert assignment.field_livestock_intake_id == intake_id
        assert assignment.count == 12
        assert assignment.status == "active"
        assert HoldingPenActivity.query.filter_by(holding_pen_id=pen_id, activity_type="assignment").count() == 1
        assert_animal_tables_not_created(db.engine)


def test_block_holding_assignment_beyond_capacity(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        pen = HoldingPen(name="Small Goat Pen", animal_type="goat", capacity_count=5, status="active")
        intake = FieldLivestockIntake(animal_type="goat", count=6, intake_status="accepted")
        db.session.add_all([pen, intake])
        db.session.commit()
        pen_id = pen.id
        intake_id = intake.id

    response = client.post(
        f"/admin/kaewa/holding-pens/{pen_id}/assign",
        data={"field_livestock_intake_id": str(intake_id)},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        assert HoldingPenAssignment.query.count() == 0


def test_block_holding_assignment_animal_type_mismatch(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        pen = HoldingPen(name="Sheep Pen", animal_type="sheep", capacity_count=20, status="active")
        intake = FieldLivestockIntake(animal_type="goat", count=4, intake_status="accepted")
        db.session.add_all([pen, intake])
        db.session.commit()
        pen_id = pen.id
        intake_id = intake.id

    response = client.post(
        f"/admin/kaewa/holding-pens/{pen_id}/assign",
        data={"field_livestock_intake_id": str(intake_id)},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        assert HoldingPenAssignment.query.count() == 0


def test_release_assignment_and_occupancy_excludes_released(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        pen = HoldingPen(name="Release Pen", animal_type="mixed", capacity_count=10, status="active")
        db.session.add(pen)
        db.session.flush()
        assignment = HoldingPenAssignment(
            holding_pen_id=pen.id,
            animal_type="cattle",
            count=3,
            status="active",
            created_by_user_id=1,
        )
        db.session.add(assignment)
        db.session.commit()
        pen_id = pen.id
        assignment_id = assignment.id

    response = client.post(
        f"/admin/kaewa/holding-assignments/{assignment_id}/release",
        data={"release_reason": "transferred_to_aggregation", "notes": "Moved out."},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        assignment = db.session.get(HoldingPenAssignment, assignment_id)
        pen = db.session.get(HoldingPen, pen_id)
        active_occupancy = sum(item.count for item in pen.assignments if item.status == "active")
        assert assignment.status == "released"
        assert assignment.released_at is not None
        assert assignment.release_reason == "transferred_to_aggregation"
        assert active_occupancy == 0
        assert HoldingPenActivity.query.filter_by(holding_pen_id=pen_id, activity_type="release").count() == 1
        assert_animal_tables_not_created(db.engine)
