from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from flask import Flask
from flask_login import LoginManager
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import (
    Cattle,
    Farmer,
    FieldLivestockIntake,
    Goat,
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
    Stakeholder.__table__,
    StakeholderActivity.__table__,
    StakeholderDocument.__table__,
    FieldLivestockIntake.__table__,
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
        for key in ("stakeholders", "activities", "documents", "intakes", "recent_activities", "recent_intakes"):
            for item in context.get(key, []):
                for attr in ("name", "subject", "title", "animal_type", "source_location", "intake_status"):
                    value = getattr(item, attr, None)
                    if value:
                        labels.append(str(value))
        for key in ("stakeholder", "intake"):
            item = context.get(key)
            if item is not None:
                for attr in ("name", "phone", "category", "animal_type", "source_location", "intake_status"):
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


def test_kaewa_routes_require_login(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()

    for path in ("/admin/kaewa", "/admin/kaewa/stakeholders", "/admin/kaewa/intakes"):
        response = client.get(path)
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
        inspector = sa.inspect(db.engine)
        assert not inspector.has_table(Goat.__tablename__)
        assert not inspector.has_table(Sheep.__tablename__)
        assert not inspector.has_table(Cattle.__tablename__)

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
        inspector = sa.inspect(db.engine)
        assert not inspector.has_table(Goat.__tablename__)
        assert not inspector.has_table(Sheep.__tablename__)
        assert not inspector.has_table(Cattle.__tablename__)

    response = client.post(
        f"/admin/kaewa/intakes/{intake_id}/status",
        data={"intake_status": "accepted"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        intake = db.session.get(FieldLivestockIntake, intake_id)
        assert intake.intake_status == "accepted"
        inspector = sa.inspect(db.engine)
        assert not inspector.has_table(Goat.__tablename__)
        assert not inspector.has_table(Sheep.__tablename__)
        assert not inspector.has_table(Cattle.__tablename__)
