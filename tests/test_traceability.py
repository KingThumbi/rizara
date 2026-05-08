from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import csv
import pytest
from flask import Flask
from flask_login import LoginManager, UserMixin

import app.routes.traceability as traceability_route
from app.models import Cattle, Goat, Sheep
from app.routes.traceability import traceability_bp
from app.services import lineage_resolver
from app.services.lineage_resolver import (
    find_animal_by_trace_token,
    get_animal_model,
    resolve_animal_lineage,
    summarize_lineage,
)
from app.services.traceability_service import animal_qr_payload


class DummyUser(UserMixin):
    def __init__(self, user_id: str, role: str):
        self.id = user_id
        self.role = role


class QueueQuery:
    def __init__(self, *, first_results=None, get_result=None, all_results=None):
        self.first_results = list(first_results or [])
        self.get_result = get_result
        self.all_results = list(all_results or [])
        self._limit = None

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, value):
        self._limit = value
        return self

    def count(self):
        return len(self.all_results)

    def first(self):
        if self.first_results:
            return self.first_results.pop(0)
        return None

    def get(self, _value):
        return self.get_result

    def all(self):
        if self._limit is None:
            return self.all_results
        return self.all_results[: self._limit]


class FakeColumn:
    def __eq__(self, _other):
        return True

    def __or__(self, _other):
        return True

    def __ge__(self, _other):
        return True

    def __le__(self, _other):
        return True

    def is_(self, _other):
        return True

    def asc(self):
        return self

    def desc(self):
        return self


class FakeAnimalModel:
    id = FakeColumn()
    qr_code_token = FakeColumn()
    trace_code = FakeColumn()
    rizara_id = FakeColumn()
    created_at = FakeColumn()
    query = QueueQuery()


class FakeEventModel:
    id = FakeColumn()
    animal_type = FakeColumn()
    animal_id = FakeColumn()
    event_datetime = FakeColumn()
    query = QueueQuery()


class EventColumn:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)

    def __ge__(self, other):
        return ("ge", self.name, other)

    def __le__(self, other):
        return ("le", self.name, other)

    def desc(self):
        return self


class EventQuery:
    def __init__(self, events):
        self.events = list(events)
        self._limit = None

    def filter(self, *criteria):
        for criterion in criteria:
            if not isinstance(criterion, tuple):
                continue

            operator, field, value = criterion
            if operator == "eq":
                self.events = [event for event in self.events if getattr(event, field, None) == value]
            elif operator == "ge":
                self.events = [event for event in self.events if getattr(event, field, None) >= value]
            elif operator == "le":
                self.events = [event for event in self.events if getattr(event, field, None) <= value]
        return self

    def order_by(self, *_args, **_kwargs):
        self.events = sorted(
            self.events,
            key=lambda event: getattr(event, "event_datetime", None) or datetime.min,
            reverse=True,
        )
        return self

    def limit(self, value):
        self._limit = value
        return self

    def all(self):
        if self._limit is None:
            return self.events
        return self.events[: self._limit]


class EventModel:
    animal_type = EventColumn("animal_type")
    event_type = EventColumn("event_type")
    source_module = EventColumn("source_module")
    event_date = EventColumn("event_date")
    event_datetime = EventColumn("event_datetime")
    query = EventQuery([])


def make_animal(**overrides):
    values = {
        "id": uuid.uuid4(),
        "rizara_id": "RZ-GOAT-2026-001",
        "trace_code": "TRACE-001",
        "qr_code_token": "qr-token",
        "status": "on_farm",
        "farmer_tag": "farm-tag",
        "source_type": None,
        "source_name": None,
        "procurement_record": None,
        "farmer": None,
        "aggregation_batch": None,
        "processing_batches": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_get_animal_model_maps_supported_types():
    assert get_animal_model("goat") is Goat
    assert get_animal_model("sheep") is Sheep
    assert get_animal_model("cattle") is Cattle
    assert get_animal_model(" Goat ") is Goat


def test_get_animal_model_rejects_invalid_type():
    with pytest.raises(ValueError):
        get_animal_model("chicken")


def test_find_animal_by_qr_code_token(monkeypatch):
    animal = make_animal()
    FakeAnimalModel.query = QueueQuery(first_results=[animal])
    monkeypatch.setitem(lineage_resolver.ANIMAL_MODELS, "goat", FakeAnimalModel)

    assert find_animal_by_trace_token("goat", "qr-token") is animal


def test_find_animal_falls_back_to_trace_code_or_rizara_id(monkeypatch):
    animal = make_animal(trace_code="TRACE-XYZ")
    FakeAnimalModel.query = QueueQuery(first_results=[None, animal])
    monkeypatch.setitem(lineage_resolver.ANIMAL_MODELS, "goat", FakeAnimalModel)

    assert find_animal_by_trace_token("goat", "TRACE-XYZ") is animal


def test_resolve_animal_lineage_returns_required_keys_with_missing_links(monkeypatch):
    animal = make_animal()

    FakeAnimalModel.query = QueueQuery(first_results=[animal])
    monkeypatch.setitem(lineage_resolver.ANIMAL_MODELS, "goat", FakeAnimalModel)
    FakeEventModel.query = QueueQuery(all_results=[])
    monkeypatch.setattr(lineage_resolver, "AnimalEvent", FakeEventModel)

    lineage = resolve_animal_lineage("goat", "qr-token")

    assert set(lineage) == {
        "animal",
        "trace_identity",
        "procurement_record",
        "farmer",
        "aggregation_batch",
        "processing_batches",
        "inventory_lots",
        "invoice_items",
        "invoices",
        "events",
    }
    assert lineage["animal"] is animal
    assert lineage["procurement_record"] is None
    assert lineage["processing_batches"] == []
    assert lineage["events"] == []


def test_summarize_lineage_returns_export_grade_sections():
    summary = summarize_lineage(
        {
            "animal": make_animal(),
            "trace_identity": {"animal_type": "goat", "trace_code": "TRACE-001"},
            "procurement_record": None,
            "farmer": None,
            "aggregation_batch": None,
            "processing_batches": [],
            "inventory_lots": [],
            "invoice_items": [],
            "invoices": [],
            "events": [],
        }
    )

    assert set(summary) == {
        "identity",
        "origin",
        "aggregation",
        "processing",
        "inventory",
        "commercial",
        "audit_trail",
    }


def make_traceability_app(monkeypatch, *, lineage=None, invalid_type=False):
    app = Flask(__name__)
    app.config.update(SECRET_KEY="test-secret", TESTING=True)

    login_manager = LoginManager()
    login_manager.init_app(app)

    users = {
        "admin": DummyUser("admin", "admin"),
        "buyer": DummyUser("buyer", "buyer"),
    }

    @login_manager.user_loader
    def load_user(user_id):
        return users.get(user_id)

    if invalid_type:
        monkeypatch.setattr(
            traceability_route,
            "resolve_animal_lineage",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("bad type")),
        )
    else:
        monkeypatch.setattr(
            traceability_route,
            "resolve_animal_lineage",
            lambda *_args, **_kwargs: lineage,
        )
        monkeypatch.setattr(
            traceability_route,
            "find_animal_by_trace_token",
            lambda *_args, **_kwargs: lineage.get("animal") if lineage else None,
        )

    monkeypatch.setattr(
        traceability_route,
        "summarize_lineage",
        lambda _lineage: {
            "identity": {"trace_code": "TRACE-001"},
            "origin": {},
            "aggregation": {},
            "processing": [],
            "inventory": [],
            "commercial": {"invoices": []},
            "audit_trail": [],
        },
    )

    app.register_blueprint(traceability_bp)
    return app


def login_as(client, user_id: str):
    with client.session_transaction() as session:
        session["_user_id"] = user_id
        session["_fresh"] = True


def test_admin_traceability_endpoint_valid_lookup(monkeypatch):
    lineage = {
        "animal": make_animal(),
        "processing_batches": [object()],
        "inventory_lots": [],
        "invoice_items": [],
        "invoices": [],
        "events": [object(), object()],
    }
    app = make_traceability_app(monkeypatch, lineage=lineage)
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability/animal/goat/qr-token.json")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["animal_type"] == "goat"
    assert payload["token"] == "qr-token"
    assert payload["summary"]["identity"] == {"trace_code": "TRACE-001"}
    assert payload["lineage_counts"]["processing_batches"] == 1
    assert payload["lineage_counts"]["events"] == 2


def test_admin_traceability_lookup_page_shows_qr_payload_fields(monkeypatch):
    lineage = {
        "animal": make_animal(),
        "trace_identity": {
            "animal_type": "goat",
            "animal_id": "animal-id",
            "rizara_id": "RZ-GOAT-2026-001",
            "trace_code": "TRACE-001",
            "qr_code_token": "qr-token",
            "status": "on_farm",
        },
        "processing_batches": [],
        "inventory_lots": [],
        "invoice_items": [],
        "invoices": [],
        "events": [],
    }
    app = make_traceability_app(monkeypatch, lineage=lineage)
    captured = {}
    monkeypatch.setattr(
        traceability_route,
        "render_template",
        lambda template, **context: captured.setdefault("context", context) or template,
    )
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability?animal_type=goat&token=qr-token")

    assert response.status_code == 200
    qr_context = captured["context"]["qr_context"]
    assert qr_context["trace_code"] == "TRACE-001"
    assert qr_context["qr_code_token"] == "qr-token"
    assert "qr-token" in qr_context["qr_payload"]
    assert qr_context["json_endpoint_url"] == "/admin/traceability/animal/goat/qr-token.json"
    assert qr_context["json_export_url"] == "/admin/traceability/animal/goat/qr-token/export.json"
    assert qr_context["qr_png_url"] == "/admin/traceability/animal/goat/qr-token/qr.png"


def test_admin_traceability_lookup_page_handles_missing_qr_payload(monkeypatch):
    animal = make_animal(trace_code=None, qr_code_token=None)
    lineage = {
        "animal": animal,
        "trace_identity": {
            "animal_type": "goat",
            "animal_id": "animal-id",
            "rizara_id": "RZ-GOAT-2026-001",
            "trace_code": None,
            "qr_code_token": None,
            "status": "on_farm",
        },
        "processing_batches": [],
        "inventory_lots": [],
        "invoice_items": [],
        "invoices": [],
        "events": [],
    }
    app = make_traceability_app(monkeypatch, lineage=lineage)
    captured = {}
    monkeypatch.setattr(
        traceability_route,
        "render_template",
        lambda template, **context: captured.setdefault("context", context) or template,
    )
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability?animal_type=goat&token=RZ-GOAT-2026-001")

    assert response.status_code == 200
    qr_context = captured["context"]["qr_context"]
    assert qr_context["qr_payload"] is None
    assert qr_context["json_endpoint_url"] is None
    assert qr_context["json_export_url"] is None
    assert animal.trace_code is None
    assert animal.qr_code_token is None


def test_admin_traceability_endpoint_invalid_token_returns_404(monkeypatch):
    app = make_traceability_app(
        monkeypatch,
        lineage={
            "animal": None,
            "processing_batches": [],
            "inventory_lots": [],
            "invoice_items": [],
            "invoices": [],
            "events": [],
        },
    )
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability/animal/goat/missing.json")

    assert response.status_code == 404


def test_admin_traceability_endpoint_invalid_type_returns_400(monkeypatch):
    app = make_traceability_app(monkeypatch, invalid_type=True)
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability/animal/chicken/token.json")

    assert response.status_code == 400


def test_traceability_endpoint_blocks_unauthenticated_request(monkeypatch):
    app = make_traceability_app(monkeypatch, lineage={"animal": make_animal()})
    response = app.test_client().get("/admin/traceability/animal/goat/token.json")

    assert response.status_code in {302, 401}


def test_traceability_endpoint_blocks_non_admin_user(monkeypatch):
    app = make_traceability_app(monkeypatch, lineage={"animal": make_animal()})
    client = app.test_client()
    login_as(client, "buyer")

    response = client.get("/admin/traceability/animal/goat/token.json")

    assert response.status_code == 403


def test_admin_traceability_lineage_export_returns_json_attachment(monkeypatch):
    lineage = {
        "animal": make_animal(),
        "processing_batches": [object()],
        "inventory_lots": [object(), object()],
        "invoice_items": [],
        "invoices": [object()],
        "events": [object()],
    }
    app = make_traceability_app(monkeypatch, lineage=lineage)
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability/animal/goat/qr-token/export.json")

    assert response.status_code == 200
    assert response.mimetype == "application/json"
    assert "attachment;" in response.headers["Content-Disposition"]
    assert "goat-qr-token-lineage.json" in response.headers["Content-Disposition"]
    payload = json.loads(response.data)
    assert payload["animal_type"] == "goat"
    assert payload["token"] == "qr-token"
    assert payload["exported_at"]
    assert payload["summary"]["identity"] == {"trace_code": "TRACE-001"}
    assert payload["lineage_counts"] == {
        "processing_batches": 1,
        "inventory_lots": 2,
        "invoice_items": 0,
        "invoices": 1,
        "events": 1,
    }


def test_admin_traceability_lineage_export_invalid_type_returns_400(monkeypatch):
    app = make_traceability_app(monkeypatch, invalid_type=True)
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability/animal/chicken/token/export.json")

    assert response.status_code == 400


def test_admin_traceability_lineage_export_invalid_token_returns_404(monkeypatch):
    app = make_traceability_app(
        monkeypatch,
        lineage={
            "animal": None,
            "processing_batches": [],
            "inventory_lots": [],
            "invoice_items": [],
            "invoices": [],
            "events": [],
        },
    )
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability/animal/goat/missing/export.json")

    assert response.status_code == 404


def test_traceability_lineage_export_blocks_unauthenticated_request(monkeypatch):
    app = make_traceability_app(monkeypatch, lineage={"animal": make_animal()})

    response = app.test_client().get("/admin/traceability/animal/goat/token/export.json")

    assert response.status_code in {302, 401}


def test_traceability_lineage_export_blocks_non_admin_user(monkeypatch):
    app = make_traceability_app(monkeypatch, lineage={"animal": make_animal()})
    client = app.test_client()
    login_as(client, "buyer")

    response = client.get("/admin/traceability/animal/goat/token/export.json")

    assert response.status_code == 403


def test_admin_traceability_qr_png_valid_request(monkeypatch):
    lineage = {"animal": make_animal()}
    app = make_traceability_app(monkeypatch, lineage=lineage)
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability/animal/goat/qr-token/qr.png")

    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert response.data.startswith(b"\x89PNG")


def test_admin_traceability_qr_png_invalid_type_returns_400(monkeypatch):
    app = make_traceability_app(monkeypatch, invalid_type=True)
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability/animal/chicken/token/qr.png")

    assert response.status_code == 400


def test_admin_traceability_qr_png_missing_token_returns_404(monkeypatch):
    app = make_traceability_app(monkeypatch, lineage={"animal": None})
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability/animal/goat/missing/qr.png")

    assert response.status_code == 404


def test_admin_traceability_qr_png_missing_payload_returns_422(monkeypatch):
    animal = make_animal(trace_code=None, qr_code_token=None)
    app = make_traceability_app(monkeypatch, lineage={"animal": animal})
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability/animal/goat/RZ-GOAT-2026-001/qr.png")

    assert response.status_code == 422
    assert animal.trace_code is None
    assert animal.qr_code_token is None


def test_admin_traceability_qr_png_blank_payload_does_not_mutate(monkeypatch):
    animal = make_animal(trace_code=" ", qr_code_token=" ")
    app = make_traceability_app(monkeypatch, lineage={"animal": animal})
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability/animal/goat/RZ-GOAT-2026-001/qr.png")

    assert response.status_code == 422
    assert animal.trace_code == " "
    assert animal.qr_code_token == " "


def test_animal_qr_payload_is_read_only_for_missing_identity():
    animal = make_animal(trace_code=None, qr_code_token=None)

    payload = animal_qr_payload(animal, "goat")

    assert payload["trace_code"] is None
    assert payload["qr_code_token"] is None
    assert payload["path"] is None
    assert animal.trace_code is None
    assert animal.qr_code_token is None


def test_traceability_qr_png_blocks_unauthenticated_request(monkeypatch):
    app = make_traceability_app(monkeypatch, lineage={"animal": make_animal()})

    response = app.test_client().get("/admin/traceability/animal/goat/token/qr.png")

    assert response.status_code in {302, 401}


def test_traceability_qr_png_blocks_non_admin_user(monkeypatch):
    app = make_traceability_app(monkeypatch, lineage={"animal": make_animal()})
    client = app.test_client()
    login_as(client, "buyer")

    response = client.get("/admin/traceability/animal/goat/token/qr.png")

    assert response.status_code == 403


class PreviewModel:
    id = FakeColumn()
    trace_code = FakeColumn()
    qr_code_token = FakeColumn()
    created_at = FakeColumn()
    query = QueueQuery()


class FakeSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def make_preview_model(animals):
    class Model:
        id = FakeColumn()
        trace_code = FakeColumn()
        qr_code_token = FakeColumn()
        created_at = FakeColumn()
        query = QueueQuery(all_results=animals)

    return Model


def patch_backfill_models(monkeypatch, *, goat_animals=None, sheep_animals=None, cattle_animals=None):
    models = {
        "goat": make_preview_model(goat_animals or []),
        "sheep": make_preview_model(sheep_animals or []),
        "cattle": make_preview_model(cattle_animals or []),
    }
    monkeypatch.setattr(traceability_route, "get_animal_model", lambda animal_type: models[animal_type])
    return models


def test_admin_backfill_preview_returns_counts_and_samples(monkeypatch):
    missing_animal = make_animal(
        trace_code=None,
        qr_code_token=None,
        source_type="market",
        source_name="Test Market",
        aggregation_batch_id=10,
        procurement_record_id=20,
    )
    PreviewModel.query = QueueQuery(all_results=[missing_animal])
    monkeypatch.setattr(traceability_route, "get_animal_model", lambda _animal_type: PreviewModel)

    captured = {}
    monkeypatch.setattr(
        traceability_route,
        "render_template",
        lambda template, **context: captured.setdefault("context", context) or template,
    )

    app = make_traceability_app(monkeypatch, lineage={"animal": None})
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability/backfill-preview")

    assert response.status_code == 200
    previews = captured["context"]["previews"]
    assert [preview["animal_type"] for preview in previews] == ["goat", "sheep", "cattle"]
    assert previews[0]["total_animals"] == 1
    assert previews[0]["missing_trace_code"] == 1
    assert previews[0]["missing_qr_code_token"] == 1
    assert previews[0]["missing_either"] == 1
    sample = previews[0]["sample"][0]
    assert set(sample) == {
        "animal_type",
        "id",
        "rizara_id",
        "status",
        "source_type",
        "source_name",
        "aggregation_batch_id",
        "procurement_record_id",
        "missing_fields",
    }
    assert sample["missing_fields"] == ["trace_code", "qr_code_token"]
    assert missing_animal.trace_code is None
    assert missing_animal.qr_code_token is None


def test_backfill_preview_blocks_unauthenticated_request(monkeypatch):
    app = make_traceability_app(monkeypatch, lineage={"animal": None})

    response = app.test_client().get("/admin/traceability/backfill-preview")

    assert response.status_code in {302, 401}


def test_backfill_preview_blocks_non_admin_user(monkeypatch):
    app = make_traceability_app(monkeypatch, lineage={"animal": None})
    client = app.test_client()
    login_as(client, "buyer")

    response = client.get("/admin/traceability/backfill-preview")

    assert response.status_code == 403


def test_backfill_identities_dry_run_does_not_mutate(monkeypatch):
    animal = make_animal(trace_code=None, qr_code_token=None)
    patch_backfill_models(monkeypatch, goat_animals=[animal])
    fake_session = FakeSession()
    monkeypatch.setattr(traceability_route.db, "session", fake_session, raising=False)

    app = make_traceability_app(monkeypatch, lineage={"animal": None})
    client = app.test_client()
    login_as(client, "admin")

    response = client.post(
        "/admin/traceability/backfill-identities",
        data={"dry_run": "yes"},
    )

    assert response.status_code == 302
    assert "backfill_status=dry_run" in response.location
    assert animal.trace_code is None
    assert animal.qr_code_token is None
    assert fake_session.commits == 0
    assert fake_session.rollbacks == 0


def test_backfill_identities_without_confirmation_does_not_mutate(monkeypatch):
    animal = make_animal(trace_code=None, qr_code_token=None)
    patch_backfill_models(monkeypatch, goat_animals=[animal])
    fake_session = FakeSession()
    monkeypatch.setattr(traceability_route.db, "session", fake_session, raising=False)

    app = make_traceability_app(monkeypatch, lineage={"animal": None})
    client = app.test_client()
    login_as(client, "admin")

    response = client.post("/admin/traceability/backfill-identities", data={})

    assert response.status_code == 302
    assert "backfill_status=missing_confirmation" in response.location
    assert animal.trace_code is None
    assert animal.qr_code_token is None
    assert fake_session.commits == 0
    assert fake_session.rollbacks == 0


def test_backfill_identities_confirmed_write_mutates_and_records_event(monkeypatch):
    animal = make_animal(trace_code=None, qr_code_token=None)
    patch_backfill_models(monkeypatch, goat_animals=[animal])
    fake_session = FakeSession()
    events = []
    monkeypatch.setattr(traceability_route.db, "session", fake_session, raising=False)
    monkeypatch.setattr(
        traceability_route,
        "record_traceability_event",
        lambda **kwargs: events.append(kwargs),
    )

    app = make_traceability_app(monkeypatch, lineage={"animal": None})
    client = app.test_client()
    login_as(client, "admin")

    response = client.post(
        "/admin/traceability/backfill-identities",
        data={"confirm_backfill": "yes"},
    )

    assert response.status_code == 302
    assert "backfill_status=success" in response.location
    assert animal.trace_code == "RZ-GOAT-2026-001"
    assert animal.qr_code_token
    assert fake_session.commits == 1
    assert fake_session.rollbacks == 0
    assert len(events) == 1
    assert events[0]["event_type"] == "trace_identity_backfilled"
    assert events[0]["source_module"] == "traceability_admin"
    assert events[0]["reference_type"] == "animal"
    assert events[0]["animal"] is animal


def test_backfill_identities_respects_max_limit(monkeypatch):
    animals = [
        make_animal(
            id=uuid.uuid4(),
            rizara_id=f"RZ-GOAT-2026-{index:03d}",
            trace_code=None,
            qr_code_token=None,
        )
        for index in range(501)
    ]
    patch_backfill_models(monkeypatch, goat_animals=animals)
    fake_session = FakeSession()
    events = []
    monkeypatch.setattr(traceability_route.db, "session", fake_session, raising=False)
    monkeypatch.setattr(
        traceability_route,
        "record_traceability_event",
        lambda **kwargs: events.append(kwargs),
    )

    app = make_traceability_app(monkeypatch, lineage={"animal": None})
    client = app.test_client()
    login_as(client, "admin")

    response = client.post(
        "/admin/traceability/backfill-identities",
        data={"confirm_backfill": "yes"},
    )

    assert response.status_code == 302
    assert "backfill_count=500" in response.location
    assert sum(1 for animal in animals if animal.trace_code) == 500
    assert len(events) == 500
    assert fake_session.commits == 1


def test_backfill_identities_blocks_unauthenticated_request(monkeypatch):
    app = make_traceability_app(monkeypatch, lineage={"animal": None})

    response = app.test_client().post("/admin/traceability/backfill-identities")

    assert response.status_code in {302, 401}


def test_backfill_identities_blocks_non_admin_user(monkeypatch):
    app = make_traceability_app(monkeypatch, lineage={"animal": None})
    client = app.test_client()
    login_as(client, "buyer")

    response = client.post("/admin/traceability/backfill-identities")

    assert response.status_code == 403


def make_event(**overrides):
    values = {
        "event_datetime": datetime(2026, 5, 7, 12, 0, 0),
        "event_date": date(2026, 5, 7),
        "animal_type": "goat",
        "animal_id": uuid.uuid4(),
        "event_type": "procured",
        "source_module": "procurement",
        "reference_type": "procurement_record",
        "reference_id": 10,
        "created_by_user_id": 1,
        "created_at": datetime(2026, 5, 7, 12, 1, 0),
        "notes": "Procured from test source.",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def patch_event_model(monkeypatch, events):
    EventModel.query = EventQuery(events)
    monkeypatch.setattr(traceability_route, "AnimalEvent", EventModel)


def test_traceability_events_admin_can_access_empty_page(monkeypatch):
    patch_event_model(monkeypatch, [])
    captured = {}
    monkeypatch.setattr(
        traceability_route,
        "render_template",
        lambda template, **context: captured.setdefault("context", context) or template,
    )
    app = make_traceability_app(monkeypatch, lineage={"animal": None})
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability/events")

    assert response.status_code == 200
    assert captured["context"]["events"] == []
    assert captured["context"]["filters"]["animal_type"] == "all"
    assert captured["context"]["limit"] == 100


def test_traceability_events_blocks_unauthenticated_request(monkeypatch):
    app = make_traceability_app(monkeypatch, lineage={"animal": None})

    response = app.test_client().get("/admin/traceability/events")

    assert response.status_code in {302, 401}


def test_traceability_events_blocks_non_admin_user(monkeypatch):
    app = make_traceability_app(monkeypatch, lineage={"animal": None})
    client = app.test_client()
    login_as(client, "buyer")

    response = client.get("/admin/traceability/events")

    assert response.status_code == 403


def test_traceability_events_filters_by_animal_type_and_event_type(monkeypatch):
    goat_event = make_event(animal_type="goat", event_type="procured")
    sheep_event = make_event(animal_type="sheep", event_type="aggregated")
    patch_event_model(monkeypatch, [goat_event, sheep_event])
    captured = {}
    monkeypatch.setattr(
        traceability_route,
        "render_template",
        lambda template, **context: captured.setdefault("context", context) or template,
    )
    app = make_traceability_app(monkeypatch, lineage={"animal": None})
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability/events?animal_type=goat&event_type=procured")

    assert response.status_code == 200
    assert len(captured["context"]["events"]) == 1
    assert captured["context"]["events"][0]["animal_type"] == "goat"
    assert captured["context"]["events"][0]["event_type"] == "procured"


def test_traceability_events_includes_event_data(monkeypatch):
    event = make_event(notes="Trace identity backfilled.")
    patch_event_model(monkeypatch, [event])
    captured = {}
    monkeypatch.setattr(
        traceability_route,
        "render_template",
        lambda template, **context: captured.setdefault("context", context) or template,
    )
    app = make_traceability_app(monkeypatch, lineage={"animal": None})
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability/events?source_module=procurement&date_from=2026-05-01&date_to=2026-05-31")

    assert response.status_code == 200
    row = captured["context"]["events"][0]
    assert row["event_datetime"] == datetime(2026, 5, 7, 12, 0, 0)
    assert row["animal_id"] == event.animal_id
    assert row["source_module"] == "procurement"
    assert row["reference_type"] == "procurement_record"
    assert row["reference_id"] == 10
    assert row["created_by_user_id"] == 1
    assert row["notes"] == "Trace identity backfilled."


def csv_rows(response):
    return list(csv.DictReader(StringIO(response.data.decode())))


def test_traceability_events_csv_admin_export_returns_csv(monkeypatch):
    event = make_event(notes="Comma, safe note")
    patch_event_model(monkeypatch, [event])
    app = make_traceability_app(monkeypatch, lineage={"animal": None})
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability/events.csv")

    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert "attachment; filename=traceability-events.csv" in response.headers["Content-Disposition"]
    rows = csv_rows(response)
    assert rows[0]["event_type"] == "procured"
    assert rows[0]["notes"] == "Comma, safe note"


def test_traceability_events_csv_blocks_unauthenticated_request(monkeypatch):
    app = make_traceability_app(monkeypatch, lineage={"animal": None})

    response = app.test_client().get("/admin/traceability/events.csv")

    assert response.status_code in {302, 401}


def test_traceability_events_csv_blocks_non_admin_user(monkeypatch):
    app = make_traceability_app(monkeypatch, lineage={"animal": None})
    client = app.test_client()
    login_as(client, "buyer")

    response = client.get("/admin/traceability/events.csv")

    assert response.status_code == 403


def test_traceability_events_csv_filters_are_honored(monkeypatch):
    goat_event = make_event(animal_type="goat", event_type="procured")
    sheep_event = make_event(animal_type="sheep", event_type="aggregated")
    patch_event_model(monkeypatch, [goat_event, sheep_event])
    app = make_traceability_app(monkeypatch, lineage={"animal": None})
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability/events.csv?animal_type=sheep&event_type=aggregated")

    assert response.status_code == 200
    rows = csv_rows(response)
    assert len(rows) == 1
    assert rows[0]["animal_type"] == "sheep"
    assert rows[0]["event_type"] == "aggregated"


def test_traceability_events_csv_empty_export_includes_headers(monkeypatch):
    patch_event_model(monkeypatch, [])
    app = make_traceability_app(monkeypatch, lineage={"animal": None})
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability/events.csv")

    assert response.status_code == 200
    header = response.data.decode().splitlines()[0]
    assert header == ",".join(traceability_route.EVENT_CSV_COLUMNS)
    assert csv_rows(response) == []


def test_traceability_events_csv_limit_cap_is_respected(monkeypatch):
    events = [
        make_event(
            animal_id=uuid.uuid4(),
            event_datetime=datetime(2026, 5, 7, 12, index % 60, 0),
        )
        for index in range(501)
    ]
    patch_event_model(monkeypatch, events)
    app = make_traceability_app(monkeypatch, lineage={"animal": None})
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability/events.csv?limit=999")

    assert response.status_code == 200
    assert len(csv_rows(response)) == 500


def sample_completeness_metrics():
    return [
        {
            "animal_type": "goat",
            "total_animals": 10,
            "with_trace_code": 8,
            "with_qr_code_token": 7,
            "missing_either": 3,
            "event_coverage": {
                event_type: 0
                for event_type in traceability_route.LIFECYCLE_EVENTS
            },
        },
        {
            "animal_type": "sheep",
            "total_animals": 4,
            "with_trace_code": 4,
            "with_qr_code_token": 3,
            "missing_either": 1,
            "event_coverage": {
                event_type: 0
                for event_type in traceability_route.LIFECYCLE_EVENTS
            },
        },
        {
            "animal_type": "cattle",
            "total_animals": 2,
            "with_trace_code": 2,
            "with_qr_code_token": 2,
            "missing_either": 0,
            "event_coverage": {
                event_type: 0
                for event_type in traceability_route.LIFECYCLE_EVENTS
            },
        },
    ]


def test_traceability_completeness_admin_can_access_dashboard(monkeypatch):
    metrics = sample_completeness_metrics()
    metrics[0]["event_coverage"]["procured"] = 6
    metrics[0]["event_coverage"]["trace_identity_backfilled"] = 2
    monkeypatch.setattr(traceability_route, "_trace_completeness_metrics", lambda: metrics)
    captured = {}
    monkeypatch.setattr(
        traceability_route,
        "render_template",
        lambda template, **context: captured.setdefault("context", context) or template,
    )
    app = make_traceability_app(monkeypatch, lineage={"animal": None})
    client = app.test_client()
    login_as(client, "admin")

    response = client.get("/admin/traceability/completeness")

    assert response.status_code == 200
    assert captured["context"]["metrics"][0]["animal_type"] == "goat"
    assert captured["context"]["metrics"][0]["total_animals"] == 10
    assert captured["context"]["metrics"][0]["with_trace_code"] == 8
    assert captured["context"]["metrics"][0]["with_qr_code_token"] == 7
    assert captured["context"]["metrics"][0]["missing_either"] == 3
    assert captured["context"]["metrics"][0]["event_coverage"]["procured"] == 6
    assert captured["context"]["metrics"][0]["event_coverage"]["trace_identity_backfilled"] == 2
    assert "inventory_created" in captured["context"]["lifecycle_events"]


def test_traceability_completeness_blocks_unauthenticated_request(monkeypatch):
    app = make_traceability_app(monkeypatch, lineage={"animal": None})

    response = app.test_client().get("/admin/traceability/completeness")

    assert response.status_code in {302, 401}


def test_traceability_completeness_blocks_non_admin_user(monkeypatch):
    app = make_traceability_app(monkeypatch, lineage={"animal": None})
    client = app.test_client()
    login_as(client, "buyer")

    response = client.get("/admin/traceability/completeness")

    assert response.status_code == 403


def test_traceability_operations_note_is_included_on_admin_pages():
    root = Path(__file__).resolve().parents[1]
    note = root / "app/templates/admin/traceability_operations_note.html"

    assert "Trace identities are created automatically" in note.read_text()
    assert "Confirmed backfill writes trace_code and qr_code_token" in note.read_text()

    for template_name in (
        "traceability_lookup.html",
        "traceability_backfill_preview.html",
        "traceability_completeness.html",
    ):
        template = root / f"app/templates/admin/{template_name}"
        assert 'include "admin/traceability_operations_note.html"' in template.read_text()
