from __future__ import annotations

from datetime import date

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.models import AggregationBatch
from app.utils.animal_helpers import animal_label, get_animal_model
from app.utils.guards import admin_required
from app.utils.request_parsers import parse_date, parse_float, parse_uuid
from app.utils.time_helpers import utcnow_naive

aggregation_bp = Blueprint("aggregation", __name__)


def commit_or_rollback(action: str) -> bool:
    try:
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        current_app.logger.exception("%s failed", action)
        flash(f"{action} failed. Please try again.", "danger")
        return False


def register_aggregation_routes(animal_type: str, template_add: str):
    Model = get_animal_model(animal_type)
    label = animal_label(animal_type)
    endpoint_name = f"add_{animal_type}_aggregation"

    @aggregation_bp.route(
        f"/{animal_type}/aggregation/add",
        methods=["GET", "POST"],
        endpoint=endpoint_name,
    )
    @admin_required
    def add_aggregation():
        available_animals = (
            Model.query
            .filter(Model.status == "on_farm")
            .filter(Model.aggregation_batch_id.is_(None))
            .order_by(Model.created_at.desc())
            .all()
        )

        if request.method == "GET":
            return render_template(
                template_add,
                animals=available_animals,
                animal_type=animal_type,
                animal_label=label,
                date=date,
                current_year=date.today().year,
            )

        site_name = (request.form.get("site_name") or "").strip()
        date_received = parse_date(request.form.get("date_received")) or date.today()
        selected_ids = request.form.getlist("animal_ids")

        if not site_name:
            flash("Site name is required.", "danger")
            return redirect(request.url)

        if not selected_ids:
            flash(f"Select at least one {label.lower()}.", "danger")
            return redirect(request.url)

        batch = AggregationBatch(
            animal_type=animal_type,
            site_name=site_name,
            date_received=date_received,
            created_by_user_id=current_user.id,
        )
        db.session.add(batch)

        attached_count = 0

        for raw_id in selected_ids:
            animal_id = parse_uuid(raw_id)
            if not animal_id:
                continue

            animal = db.session.get(Model, animal_id)
            if not animal:
                continue

            if (animal.status or "").strip().lower() != "on_farm":
                continue

            if animal.aggregation_batch_id is not None:
                continue

            animal.live_weight_kg = parse_float(request.form.get(f"weight_{raw_id}"))
            animal.purchase_price_per_head = parse_float(request.form.get(f"price_{raw_id}"))
            animal.weight_method = (request.form.get(f"method_{raw_id}") or "scale").strip() or "scale"
            animal.purchase_currency = "KES"
            animal.status = "aggregated"
            animal.aggregation_batch = batch
            animal.aggregated_at = utcnow_naive()
            animal.aggregated_by_user_id = current_user.id

            attached_count += 1

        if attached_count == 0:
            db.session.rollback()
            flash(
                f"No {label.lower()} were aggregated. "
                f"Please select animals that are still on farm and not already assigned to a batch.",
                "danger",
            )
            return redirect(request.url)

        if not commit_or_rollback(f"Create {label} aggregation batch"):
            return redirect(request.url)

        flash(f"{label} aggregation batch created successfully ({attached_count} animals).", "success")
        return redirect(url_for("main.dashboard"))

    @aggregation_bp.route(
        f"/{animal_type}/aggregation",
        methods=["GET"],
        endpoint=f"list_{animal_type}_aggregation",
    )
    @admin_required
    def list_aggregation_batches():
        batches = (
            AggregationBatch.query
            .filter(AggregationBatch.animal_type == animal_type)
            .order_by(AggregationBatch.created_at.desc())
            .all()
        )

        return render_template(
            "aggregation/batch_list.html",
            batches=batches,
            animal_type=animal_type,
            animal_label=label,
            current_year=date.today().year,
        )


register_aggregation_routes("goat", "aggregation/batch_add.html")
register_aggregation_routes("sheep", "aggregation/batch_add.html")
register_aggregation_routes("cattle", "aggregation/batch_add.html")