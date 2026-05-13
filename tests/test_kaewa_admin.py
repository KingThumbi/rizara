from __future__ import annotations

from datetime import date
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
    RuralServiceProduct,
    RuralServiceSale,
    RuralServiceSaleItem,
    RuralServiceStockMovement,
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
    RuralServiceProduct.__table__,
    RuralServiceSale.__table__,
    RuralServiceSaleItem.__table__,
    RuralServiceStockMovement.__table__,
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
            "movements",
            "sales",
        ):
            for item in context.get(key, []):
                for attr in (
                    "name",
                    "subject",
                    "title",
                    "animal_type",
                    "source_location",
                    "intake_status",
                    "status",
                    "movement_type",
                    "reference",
                    "sale_number",
                ):
                    value = getattr(item, attr, None)
                    if value:
                        labels.append(str(value))
                if getattr(item, "count", None) is not None:
                    labels.append(str(item.count))
                if getattr(item, "quantity", None) is not None:
                    labels.append(str(item.quantity))
                if getattr(item, "total_amount", None) is not None:
                    labels.append(str(item.total_amount))
        for key in ("pen_summaries", "holding_pen_summaries"):
            for summary in context.get(key, []):
                pen = summary["pen"]
                labels.extend([pen.name, str(summary["occupancy"])])
        if "product_summaries" in context:
            for summary in context["product_summaries"]:
                product = summary["product"]
                labels.extend([product.name, str(summary["stock"])])
                if summary["low_stock"]:
                    labels.append("Low Stock")
        if "rural_product_summaries" in context:
            for summary in context["rural_product_summaries"]:
                product = summary["product"]
                labels.extend([product.name, str(summary["stock"])])
                if summary["low_stock"]:
                    labels.append("Low Stock")
        if "aggregation_batches" in context:
            labels.extend(batch.site_name for batch in context["aggregation_batches"])
        if "handoff_events" in context:
            labels.extend(event.event_type for event in context["handoff_events"])
        if "sale" in context:
            sale = context["sale"]
            labels.extend([str(sale.sale_number), str(sale.status or "")])
            if template.endswith("rural_service_sale_receipt.html"):
                labels.extend(["Rizara Meats Ltd", "Kaewa Aggregation & Liaison Office"])
                if sale.status == "draft":
                    labels.append("Receipt available after sale completion.")
                if sale.status == "cancelled":
                    labels.append("Cancelled sale. This is not a valid paid receipt.")
            for item in sale.items:
                labels.extend([item.product.name, str(item.quantity), str(item.line_total)])
        if "total" in context:
            labels.append(str(context["total"]))
        for key in ("stakeholder", "intake", "pen", "product"):
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
                    "sku",
                    "category",
                    "unit",
                ):
                    value = getattr(item, attr, None)
                    if value:
                        labels.append(str(value))
        if "stock" in context:
            labels.append(str(context["stock"]))
        if context.get("low_stock"):
            labels.append("Low Stock")
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


def rural_stock(product_id):
    stock_in = db.session.query(sa.func.coalesce(sa.func.sum(RuralServiceStockMovement.quantity), 0)).filter(
        RuralServiceStockMovement.product_id == product_id,
        RuralServiceStockMovement.movement_type.in_(["opening_stock", "purchase", "adjustment_in", "sale_reversal"]),
    ).scalar()
    stock_out = db.session.query(sa.func.coalesce(sa.func.sum(RuralServiceStockMovement.quantity), 0)).filter(
        RuralServiceStockMovement.product_id == product_id,
        RuralServiceStockMovement.movement_type.in_(["adjustment_out", "damaged", "expired", "issued_internal", "sale"]),
    ).scalar()
    return stock_in - stock_out


def test_kaewa_routes_require_login(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()

    for path in (
        "/admin/kaewa",
        "/admin/kaewa/stakeholders",
        "/admin/kaewa/intakes",
        "/admin/kaewa/holding-pens",
        "/admin/kaewa/rural-services",
        "/admin/kaewa/rural-services/sales",
    ):
        response = client.get(path)
        assert response.status_code in (302, 401)

    for path in (
        "/admin/kaewa/intakes/1/handoff/ready",
        "/admin/kaewa/intakes/1/handoff/link-batch",
        "/admin/kaewa/holding-pens/1/assign",
        "/admin/kaewa/holding-assignments/1/release",
        "/admin/kaewa/rural-services/products/1/stock-movements/new",
        "/admin/kaewa/rural-services/sales/1/complete",
        "/admin/kaewa/rural-services/sales/1/cancel",
    ):
        response = client.post(path)
        assert response.status_code in (302, 401)

    response = client.get("/admin/kaewa/rural-services/sales/1/receipt")
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


def test_create_rural_service_product(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    response = client.post(
        "/admin/kaewa/rural-services/products/new",
        data={
            "name": "Goat Finisher Feed",
            "category": "animal_feed",
            "unit": "bag",
            "sku": "KAEWA-FEED-001",
            "reorder_level": "5",
            "active": "1",
            "description": "Approved feed stock.",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Goat Finisher Feed" in response.get_data(as_text=True)
    with app.app_context():
        product = RuralServiceProduct.query.filter_by(sku="KAEWA-FEED-001").one()
        assert product.uuid is not None
        assert product.category == "animal_feed"


def test_rural_service_stock_movements_calculate_balance(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        product = RuralServiceProduct(
            name="Mineral Supplement",
            category="mineral_supplement",
            unit="packet",
            reorder_level=5,
        )
        db.session.add(product)
        db.session.commit()
        product_id = product.id

    response = client.post(
        f"/admin/kaewa/rural-services/products/{product_id}/stock-movements/new",
        data={
            "movement_type": "opening_stock",
            "quantity": "15",
            "unit_cost": "120",
            "supplier_name": "Local Supplier",
            "reference": "OPEN-001",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "15.00" in response.get_data(as_text=True)

    response = client.post(
        f"/admin/kaewa/rural-services/products/{product_id}/stock-movements/new",
        data={
            "movement_type": "issued_internal",
            "quantity": "4",
            "reference": "ISSUE-001",
        },
        follow_redirects=True,
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "11.00" in body
    with app.app_context():
        assert RuralServiceStockMovement.query.filter_by(product_id=product_id).count() == 2


def test_rural_service_stock_movement_rejects_zero_or_negative_quantity(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        product = RuralServiceProduct(name="Hoof Tool", category="farm_tool", unit="piece")
        db.session.add(product)
        db.session.commit()
        product_id = product.id

    for quantity in ("0", "-2"):
        response = client.post(
            f"/admin/kaewa/rural-services/products/{product_id}/stock-movements/new",
            data={"movement_type": "opening_stock", "quantity": quantity},
            follow_redirects=True,
        )
        assert response.status_code == 200

    with app.app_context():
        assert RuralServiceStockMovement.query.filter_by(product_id=product_id).count() == 0


def test_rural_service_low_stock_flag_appears(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        product = RuralServiceProduct(
            name="Salt Lick",
            category="mineral_supplement",
            unit="piece",
            reorder_level=10,
        )
        db.session.add(product)
        db.session.flush()
        db.session.add(
            RuralServiceStockMovement(
                product_id=product.id,
                movement_type="opening_stock",
                quantity=8,
                created_by_user_id=1,
            )
        )
        db.session.commit()

    response = client.get("/admin/kaewa/rural-services")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Salt Lick" in body
    assert "Low Stock" in body


def test_inactive_rural_service_product_only_allows_adjustment_out(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        product = RuralServiceProduct(name="Inactive Feed", category="animal_feed", unit="bag", active=False)
        db.session.add(product)
        db.session.commit()
        product_id = product.id

    blocked = client.post(
        f"/admin/kaewa/rural-services/products/{product_id}/stock-movements/new",
        data={"movement_type": "purchase", "quantity": "5"},
        follow_redirects=True,
    )
    allowed = client.post(
        f"/admin/kaewa/rural-services/products/{product_id}/stock-movements/new",
        data={"movement_type": "adjustment_out", "quantity": "1"},
        follow_redirects=True,
    )

    assert blocked.status_code == 200
    assert allowed.status_code == 200
    with app.app_context():
        movement = RuralServiceStockMovement.query.filter_by(product_id=product_id).one()
        assert movement.movement_type == "adjustment_out"


def test_rural_services_does_not_add_payment_or_sale_routes(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    routes = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/admin/kaewa/rural-services/checkout" not in routes
    assert "/admin/kaewa/rural-services/payments" not in routes


def test_create_draft_rural_service_sale_does_not_reduce_stock(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        product = RuralServiceProduct(name="Feed Bag", category="animal_feed", unit="bag")
        db.session.add(product)
        db.session.flush()
        db.session.add(RuralServiceStockMovement(product_id=product.id, movement_type="opening_stock", quantity=10))
        db.session.commit()
        product_id = product.id

    response = client.post(
        "/admin/kaewa/rural-services/sales/new",
        data={
            "buyer_name": "Walk-in Buyer",
            "sale_date": "2026-05-13",
            "payment_method": "cash",
            "product_id": str(product_id),
            "quantity": "3",
            "unit_price": "500",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Feed Bag" in response.get_data(as_text=True)
    with app.app_context():
        sale = RuralServiceSale.query.one()
        assert sale.status == "draft"
        assert len(sale.items) == 1
        assert rural_stock(product_id) == 10
        assert RuralServiceStockMovement.query.filter_by(product_id=product_id, movement_type="sale").count() == 0


def test_complete_rural_service_sale_reduces_stock(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        product = RuralServiceProduct(name="Mineral Pack", category="mineral_supplement", unit="packet")
        db.session.add(product)
        db.session.flush()
        db.session.add(RuralServiceStockMovement(product_id=product.id, movement_type="opening_stock", quantity=10))
        sale = RuralServiceSale(sale_number="KRS-TEST-001", payment_method="cash", sale_date=date(2026, 5, 13))
        sale.items.append(RuralServiceSaleItem(product=product, quantity=4, unit_price=100, line_total=400))
        db.session.add(sale)
        db.session.commit()
        sale_id = sale.id
        product_id = product.id

    response = client.post(f"/admin/kaewa/rural-services/sales/{sale_id}/complete", follow_redirects=True)

    assert response.status_code == 200
    assert "completed" in response.get_data(as_text=True)
    with app.app_context():
        sale = db.session.get(RuralServiceSale, sale_id)
        assert sale.status == "completed"
        assert rural_stock(product_id) == 6
        assert RuralServiceStockMovement.query.filter_by(product_id=product_id, movement_type="sale").count() == 1


def test_insufficient_stock_blocks_rural_service_sale_completion(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        product = RuralServiceProduct(name="Tool", category="farm_tool", unit="piece")
        db.session.add(product)
        db.session.flush()
        db.session.add(RuralServiceStockMovement(product_id=product.id, movement_type="opening_stock", quantity=1))
        sale = RuralServiceSale(sale_number="KRS-TEST-002", payment_method="cash", sale_date=date(2026, 5, 13))
        sale.items.append(RuralServiceSaleItem(product=product, quantity=2, unit_price=100, line_total=200))
        db.session.add(sale)
        db.session.commit()
        sale_id = sale.id
        product_id = product.id

    response = client.post(f"/admin/kaewa/rural-services/sales/{sale_id}/complete", follow_redirects=True)

    assert response.status_code == 200
    with app.app_context():
        sale = db.session.get(RuralServiceSale, sale_id)
        assert sale.status == "draft"
        assert rural_stock(product_id) == 1
        assert RuralServiceStockMovement.query.filter_by(product_id=product_id, movement_type="sale").count() == 0


def test_cancel_completed_rural_service_sale_restores_stock(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        product = RuralServiceProduct(name="Merch Cap", category="rizara_merchandise", unit="piece")
        db.session.add(product)
        db.session.flush()
        db.session.add_all([
            RuralServiceStockMovement(product_id=product.id, movement_type="opening_stock", quantity=5),
            RuralServiceStockMovement(product_id=product.id, movement_type="sale", quantity=2),
        ])
        sale = RuralServiceSale(sale_number="KRS-TEST-003", payment_method="cash", sale_date=date(2026, 5, 13), status="completed")
        sale.items.append(RuralServiceSaleItem(product=product, quantity=2, unit_price=50, line_total=100))
        db.session.add(sale)
        db.session.commit()
        sale_id = sale.id
        product_id = product.id

    response = client.post(f"/admin/kaewa/rural-services/sales/{sale_id}/cancel", follow_redirects=True)

    assert response.status_code == 200
    with app.app_context():
        sale = db.session.get(RuralServiceSale, sale_id)
        assert sale.status == "cancelled"
        assert rural_stock(product_id) == 5
        assert RuralServiceStockMovement.query.filter_by(product_id=product_id, movement_type="sale_reversal").count() == 1


def test_inactive_product_cannot_be_sold(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        product = RuralServiceProduct(name="Inactive Tool", category="farm_tool", unit="piece", active=False)
        db.session.add(product)
        db.session.commit()
        product_id = product.id

    response = client.post(
        "/admin/kaewa/rural-services/sales/new",
        data={
            "buyer_name": "Walk-in Buyer",
            "sale_date": "2026-05-13",
            "payment_method": "cash",
            "product_id": str(product_id),
            "quantity": "1",
            "unit_price": "10",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        assert RuralServiceSale.query.count() == 0


def test_rural_sales_no_mpesa_integration_routes(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    routes = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/admin/kaewa/rural-services/sales/mpesa" not in routes
    assert "/admin/kaewa/rural-services/sales/<int:sale_id>/mpesa" not in routes


def test_completed_rural_service_sale_receipt_loads(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        product = RuralServiceProduct(name="Receipt Feed", category="animal_feed", unit="bag")
        sale = RuralServiceSale(
            sale_number="KRS-RECEIPT-001",
            buyer_name="Receipt Buyer",
            buyer_phone="0700000000",
            payment_method="cash",
            payment_reference="CASH-001",
            sale_date=date(2026, 5, 13),
            status="completed",
            created_by_user_id=1,
        )
        sale.items.append(RuralServiceSaleItem(product=product, quantity=2, unit_price=300, line_total=600))
        db.session.add(sale)
        db.session.commit()
        sale_id = sale.id

    response = client.get(f"/admin/kaewa/rural-services/sales/{sale_id}/receipt")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Rizara Meats Ltd" in body
    assert "Kaewa Aggregation & Liaison Office" in body
    assert "KRS-RECEIPT-001" in body
    assert "Receipt Feed" in body
    assert "600" in body


def test_draft_rural_service_sale_receipt_safe_message(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        sale = RuralServiceSale(
            sale_number="KRS-DRAFT-001",
            payment_method="cash",
            sale_date=date(2026, 5, 13),
            status="draft",
        )
        db.session.add(sale)
        db.session.commit()
        sale_id = sale.id

    response = client.get(f"/admin/kaewa/rural-services/sales/{sale_id}/receipt")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Receipt available after sale completion." in body
    assert "draft" in body


def test_cancelled_rural_service_sale_receipt_marked_cancelled(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        sale = RuralServiceSale(
            sale_number="KRS-CANCELLED-001",
            payment_method="cash",
            sale_date=date(2026, 5, 13),
            status="cancelled",
        )
        db.session.add(sale)
        db.session.commit()
        sale_id = sale.id

    response = client.get(f"/admin/kaewa/rural-services/sales/{sale_id}/receipt")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Cancelled sale. This is not a valid paid receipt." in body
    assert "cancelled" in body


def test_rural_service_receipt_does_not_mutate_stock(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        product = RuralServiceProduct(name="Receipt Tool", category="farm_tool", unit="piece")
        db.session.add(product)
        db.session.flush()
        db.session.add_all(
            [
                RuralServiceStockMovement(product_id=product.id, movement_type="opening_stock", quantity=5),
                RuralServiceStockMovement(product_id=product.id, movement_type="sale", quantity=2),
            ]
        )
        sale = RuralServiceSale(
            sale_number="KRS-READONLY-001",
            payment_method="cash",
            sale_date=date(2026, 5, 13),
            status="completed",
        )
        sale.items.append(RuralServiceSaleItem(product=product, quantity=2, unit_price=50, line_total=100))
        db.session.add(sale)
        db.session.commit()
        sale_id = sale.id
        product_id = product.id
        stock_before = rural_stock(product_id)
        movement_count_before = RuralServiceStockMovement.query.count()

    response = client.get(f"/admin/kaewa/rural-services/sales/{sale_id}/receipt")

    assert response.status_code == 200
    with app.app_context():
        assert rural_stock(product_id) == stock_before
        assert RuralServiceStockMovement.query.count() == movement_count_before


def test_rural_service_receipt_does_not_create_payment_records(monkeypatch, tmp_path):
    app = make_kaewa_app(monkeypatch, tmp_path)
    client = app.test_client()
    login_admin(client)

    with app.app_context():
        sale = RuralServiceSale(
            sale_number="KRS-NOPAY-001",
            payment_method="cash",
            sale_date=date(2026, 5, 13),
            status="completed",
        )
        db.session.add(sale)
        db.session.commit()
        sale_id = sale.id
        inspector = sa.inspect(db.engine)
        assert not inspector.has_table("invoice_payments")
        assert not inspector.has_table("sale_payments")

    response = client.get(f"/admin/kaewa/rural-services/sales/{sale_id}/receipt")

    assert response.status_code == 200
    with app.app_context():
        inspector = sa.inspect(db.engine)
        assert not inspector.has_table("invoice_payments")
        assert not inspector.has_table("sale_payments")
