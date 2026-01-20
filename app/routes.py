# app/routes.py

import os
import uuid
import requests
from functools import wraps
from datetime import date, datetime

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    current_app,
    send_from_directory,
)
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from .extensions import db, limiter
from .utils.guards import admin_required
from .utils.invoice_pdf import render_invoice_pdf  # PDF renderer (no DB writes)

from .models import (
    User,
    Farmer,
    Goat,
    Sheep,
    Cattle,
    AggregationBatch,
    ProcessingBatch,
    ContactMessage,
    OrderRequest,
    ProcessingYield,
    Buyer,
    ProcessingBatchSale,
    Invoice,
    InvoiceItem,
    InvoiceStatus,  # ✅ Enum
)

main = Blueprint("main", __name__)


# ======================
# Buyer Guard (PORTAL)
# ======================
def buyer_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if (getattr(current_user, "role", "") or "").lower() != "buyer":
            flash("Access denied.", "danger")
            return redirect(url_for("main.dashboard"))
        return view(*args, **kwargs)
    return wrapped


def _get_buyer_for_current_user_or_404():
    buyer = Buyer.query.filter_by(user_id=current_user.id).first()
    if not buyer:
        flash("Buyer profile not linked to this account. Contact Rizara support/admin.", "danger")
        return redirect(url_for("auth.logout"))
    return buyer


# ======================
# Home
# ======================
@main.route("/")
def home():
    return redirect(url_for("main.dashboard"))


# ======================
# Favicon
# ======================
@main.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(current_app.root_path, "static"),
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )


# ======================
# Helpers
# ======================
def _parse_float(val):
    try:
        if val is None or str(val).strip() == "":
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


def _parse_int(val):
    try:
        if val is None or str(val).strip() == "":
            return None
        return int(val)
    except (TypeError, ValueError):
        return None


def _parse_date(val):
    try:
        if not val:
            return None
        return date.fromisoformat(val)
    except (TypeError, ValueError):
        return None


def _parse_uuid(val):
    try:
        if val is None:
            return None
        s = str(val).strip()
        if not s:
            return None
        return uuid.UUID(s)
    except Exception:
        return None


def _safe_enum_value(v):
    """
    For templates / display:
    - If v is Enum -> return its `.value`
    - Else -> return v
    """
    try:
        return v.value
    except Exception:
        return v


# ======================
# reCAPTCHA Verification
# ======================
def verify_recaptcha(response_token: str) -> bool:
    secret = (
        current_app.config.get("RECAPTCHA_SECRET_KEY") if current_app else None
    ) or os.getenv("RECAPTCHA_SECRET_KEY") or "6Lc1hEksAAAAAJjGH2S0KcW6kyOye7bs927dN_hW"

    if not response_token:
        return False

    try:
        r = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={"secret": secret, "response": response_token},
            timeout=5,
        )
        return bool(r.json().get("success", False))
    except Exception as e:
        print("reCAPTCHA verification failed:", e)
        return False


# ======================
# Dashboard (ADMIN ONLY)
# ======================
@main.route("/dashboard")
@admin_required
def dashboard():
    stats = {
        "farmers": Farmer.query.count(),
        "goats": Goat.query.count(),
        "sheep": Sheep.query.count(),
        "cattle": Cattle.query.count(),
        "aggregation_batches": AggregationBatch.query.count(),
        "processing_batches": ProcessingBatch.query.count(),
    }

    stats["goat_pipeline"] = {
        "on_farm": Goat.query.filter_by(status="on_farm").count(),
        "aggregated": Goat.query.filter_by(status="aggregated").count(),
        "processing": Goat.query.filter_by(status="processing").count(),
        "processed": Goat.query.filter_by(status="processed").count(),
        "sold": Goat.query.filter_by(status="sold").count(),
    }
    stats["sheep_pipeline"] = {
        "on_farm": Sheep.query.filter_by(status="on_farm").count(),
        "aggregated": Sheep.query.filter_by(status="aggregated").count(),
        "processing": Sheep.query.filter_by(status="processing").count(),
        "processed": Sheep.query.filter_by(status="processed").count(),
        "sold": Sheep.query.filter_by(status="sold").count(),
    }
    stats["cattle_pipeline"] = {
        "on_farm": Cattle.query.filter_by(status="on_farm").count(),
        "aggregated": Cattle.query.filter_by(status="aggregated").count(),
        "processing": Cattle.query.filter_by(status="processing").count(),
        "processed": Cattle.query.filter_by(status="processed").count(),
        "sold": Cattle.query.filter_by(status="sold").count(),
    }

    stats["latest_contacts"] = (
        ContactMessage.query.order_by(ContactMessage.created_at.desc()).limit(5).all()
    )
    stats["latest_orders"] = (
        OrderRequest.query.order_by(OrderRequest.created_at.desc()).limit(5).all()
    )

    return render_template(
        "dashboard.html",
        stats=stats,
        goat_pipeline=stats.get("goat_pipeline", {}),
        sheep_pipeline=stats.get("sheep_pipeline", {}),
        cattle_pipeline=stats.get("cattle_pipeline", {}),
        current_year=datetime.utcnow().year,
    )


# ======================
# Farmer Routes (ADMIN ONLY)
# ======================
@main.route("/farmers/add", methods=["GET", "POST"])
@admin_required
def add_farmer():
    if request.method == "POST":
        farmer = Farmer(
            name=request.form.get("name"),
            phone=request.form.get("phone"),
            county=request.form.get("county"),
            ward=request.form.get("ward"),
            village=request.form.get("village"),
            latitude=_parse_float(request.form.get("latitude")),
            longitude=_parse_float(request.form.get("longitude")),
            location_notes=request.form.get("location_notes"),
        )
        db.session.add(farmer)
        db.session.commit()
        flash("Farmer added successfully", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("farmers/add.html")


# ======================
# Animal Utilities
# ======================
def generate_animal_code(animal_type: str, farmer_id: int) -> str:
    year = datetime.utcnow().year
    model_map = {"goat": Goat, "sheep": Sheep, "cattle": Cattle}
    Model = model_map.get(animal_type)
    if Model is None:
        return f"RZ-{animal_type.upper()}-{year}-{farmer_id}-001"

    last_animal = (
        Model.query.filter(Model.farmer_id == farmer_id, Model.rizara_id.like("RZ-%"))
        .order_by(Model.created_at.desc())
        .first()
    )

    last_seq = 0
    if last_animal and getattr(last_animal, "rizara_id", None):
        try:
            last_seq = int(last_animal.rizara_id.split("-")[-1])
        except (ValueError, IndexError):
            last_seq = 0

    return f"RZ-{animal_type.upper()}-{year}-{farmer_id}-{last_seq + 1:03d}"


# ======================
# Add Animals (ADMIN ONLY)
# ======================
@main.route("/goats/add", methods=["GET", "POST"])
@admin_required
def add_goat():
    farmers = Farmer.query.all()
    if request.method == "POST":
        farmer_id = _parse_int(request.form.get("farmer_id"))
        if not farmer_id:
            flash("Select a farmer.", "danger")
            return redirect(request.url)

        farmer = Farmer.query.get_or_404(farmer_id)
        goat = Goat(
            farmer_tag=farmer.name,
            rizara_id=generate_animal_code("goat", farmer_id),
            sex=request.form.get("sex"),
            breed=request.form.get("breed"),
            estimated_dob=_parse_date(request.form.get("estimated_dob")),
            farmer_id=farmer_id,
            status="on_farm",
        )
        db.session.add(goat)
        db.session.commit()
        flash("Goat registered successfully", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("goats/add.html", farmers=farmers)


@main.route("/sheep/add", methods=["GET", "POST"])
@admin_required
def add_sheep():
    farmers = Farmer.query.all()
    if request.method == "POST":
        farmer_id = _parse_int(request.form.get("farmer_id"))
        if not farmer_id:
            flash("Select a farmer.", "danger")
            return redirect(request.url)

        farmer = Farmer.query.get_or_404(farmer_id)
        sheep = Sheep(
            farmer_tag=farmer.name,
            rizara_id=generate_animal_code("sheep", farmer_id),
            sex=request.form.get("sex"),
            breed=request.form.get("breed"),
            estimated_dob=_parse_date(request.form.get("estimated_dob")),
            farmer_id=farmer_id,
            status="on_farm",
        )
        db.session.add(sheep)
        db.session.commit()
        flash("Sheep registered successfully", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("sheep/add.html", farmers=farmers)


@main.route("/cattle/add", methods=["GET", "POST"])
@admin_required
def add_cattle():
    farmers = Farmer.query.all()
    if request.method == "POST":
        farmer_id = _parse_int(request.form.get("farmer_id"))
        if not farmer_id:
            flash("Select a farmer.", "danger")
            return redirect(request.url)

        farmer = Farmer.query.get_or_404(farmer_id)
        cattle = Cattle(
            farmer_tag=farmer.name,
            rizara_id=generate_animal_code("cattle", farmer_id),
            sex=request.form.get("sex"),
            breed=request.form.get("breed"),
            estimated_dob=_parse_date(request.form.get("estimated_dob")),
            farmer_id=farmer_id,
            status="on_farm",
        )
        db.session.add(cattle)
        db.session.commit()
        flash("Cattle registered successfully", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("cattle/add.html", farmers=farmers)


# ======================
# Aggregation Batches (ADMIN ONLY)
# ======================
def aggregation_route(animal_type: str, template_add: str):
    model_map = {"goat": Goat, "sheep": Sheep, "cattle": Cattle}
    Model = model_map[animal_type]
    label = animal_type.capitalize()
    endpoint_name = f"add_{animal_type}_aggregation"

    @main.route(f"/{animal_type}/aggregation/add", methods=["GET", "POST"], endpoint=endpoint_name)
    @admin_required
    def add_aggregation():
        available_animals = (
            Model.query.filter(Model.status == "on_farm")
            .filter(Model.aggregation_batch_id.is_(None))
            .order_by(Model.created_at.desc())
            .all()
        )

        if request.method == "POST":
            site_name = (request.form.get("site_name") or "").strip()
            date_received = _parse_date(request.form.get("date_received"))
            animal_ids = request.form.getlist("animal_ids")

            if not site_name or not animal_ids:
                flash("Site name and at least one animal are required", "danger")
                return redirect(request.url)

            batch = AggregationBatch(
                animal_type=animal_type,
                site_name=site_name,
                date_received=date_received or date.today(),
                created_by_user_id=current_user.id,
            )
            db.session.add(batch)

            attached = 0
            for a_id in animal_ids:
                a_uuid = _parse_uuid(a_id)
                if not a_uuid:
                    continue

                animal = db.session.get(Model, a_uuid)
                if not animal:
                    continue

                if (animal.status or "").strip() != "on_farm":
                    continue
                if animal.aggregation_batch_id is not None:
                    continue

                weight = _parse_float(request.form.get(f"weight_{a_id}"))
                price = _parse_float(request.form.get(f"price_{a_id}"))
                method = (request.form.get(f"method_{a_id}") or "scale").strip()

                animal.live_weight_kg = weight
                animal.weight_method = method
                animal.purchase_price_per_head = price
                animal.purchase_currency = "KES"
                animal.aggregated_at = datetime.utcnow()
                animal.aggregated_by_user_id = current_user.id
                animal.status = "aggregated"
                animal.aggregation_batch = batch

                attached += 1

            if attached == 0:
                db.session.rollback()
                flash(
                    f"No {label.lower()} were aggregated. Confirm you selected animals that are still 'on_farm' and not already in a batch.",
                    "danger",
                )
                return redirect(request.url)

            db.session.commit()
            flash(f"{label} aggregation batch created successfully ({attached} animals)", "success")
            return redirect(url_for("main.dashboard"))

        return render_template(template_add, animals=available_animals, date=date)

    return add_aggregation


aggregation_route("goat", "aggregation/goats_add.html")
aggregation_route("sheep", "aggregation/sheep_add.html")
aggregation_route("cattle", "aggregation/cattle_add.html")


# ======================
# Processing Batches (ADMIN ONLY)
# ======================
def processing_route(animal_type: str, template_add: str):
    model_map = {"goat": Goat, "sheep": Sheep, "cattle": Cattle}
    Model = model_map[animal_type]
    label = animal_type.capitalize()
    endpoint_name = f"add_{animal_type}_processing"

    @main.route(f"/{animal_type}/processing/add", methods=["GET", "POST"], endpoint=endpoint_name)
    @admin_required
    def add_processing():
        available_animals = (
            Model.query.filter(Model.status == "aggregated")
            .order_by(Model.created_at.desc())
            .all()
        )

        if request.method == "POST":
            facility = (request.form.get("facility") or "").strip()
            slaughter_date = _parse_date(request.form.get("slaughter_date"))
            halal_cert_ref = (request.form.get("halal_cert_ref") or "").strip() or None
            animal_ids = request.form.getlist("animal_ids")

            if not facility or not animal_ids:
                flash("Facility and at least one animal are required", "danger")
                return redirect(request.url)

            batch = ProcessingBatch(
                animal_type=animal_type,
                facility=facility,
                slaughter_date=slaughter_date,
                halal_cert_ref=halal_cert_ref,
                created_by_user_id=current_user.id,
            )

            attached = 0
            for a_id in animal_ids:
                a_uuid = _parse_uuid(a_id)
                if not a_uuid:
                    continue

                animal = db.session.get(Model, a_uuid)
                if not animal:
                    continue

                if (animal.status or "").strip() != "aggregated":
                    continue

                animal.status = "processing"

                if animal_type == "goat":
                    batch.goats.append(animal)
                elif animal_type == "sheep":
                    batch.sheep.append(animal)
                elif animal_type == "cattle":
                    batch.cattle.append(animal)

                attached += 1

            if attached == 0:
                db.session.rollback()
                flash(
                    f"No {label.lower()} were moved to processing. Confirm you selected animals that are still 'aggregated'.",
                    "danger",
                )
                return redirect(request.url)

            db.session.add(batch)
            db.session.commit()
            flash(f"{label} processing batch created successfully ({attached} animals)", "success")
            return redirect(url_for("main.view_invoiceable_batch", batch_id=batch.id))

        return render_template(template_add, animals=available_animals, date=date)

    return add_processing


processing_route("goat", "processing/goats_add.html")
processing_route("sheep", "processing/sheep_add.html")
processing_route("cattle", "processing/cattle_add.html")


# ======================
# Public Forms (PUBLIC)
# ======================
@main.route("/submit-contact", methods=["POST"])
@limiter.limit("5 per minute")
def submit_contact():
    if request.form.get("hp_field"):
        return jsonify({"success": False}), 200

    if not verify_recaptcha(request.form.get("g-recaptcha-response")):
        return jsonify({"success": False}), 403

    name = request.form.get("name")
    email = request.form.get("email")
    phone = request.form.get("phone")
    message = request.form.get("message")

    if not name or not email or not message:
        return jsonify({"success": False}), 400

    contact = ContactMessage(
        name=name,
        email=email,
        subject=f"Website contact form - {phone}",
        message=message,
        status="new",
    )
    db.session.add(contact)
    db.session.commit()
    return jsonify({"success": True}), 200


@main.route("/submit-order", methods=["POST"])
@limiter.limit("3 per minute")
def submit_order():
    if request.form.get("hp_field"):
        return jsonify({"success": False}), 200

    if not verify_recaptcha(request.form.get("g-recaptcha-response")):
        return jsonify({"success": False}), 403

    buyer_name = request.form.get("buyerName")
    email = request.form.get("email")
    phone = request.form.get("phone")
    product = request.form.get("product")
    quantity = request.form.get("quantity")
    destination = request.form.get("destination")
    notes = request.form.get("message")

    qty_int = _parse_int(quantity)
    if not all([buyer_name, email, phone, product, qty_int, destination]):
        return jsonify({"success": False}), 400

    order = OrderRequest(
        buyer_name=buyer_name,
        phone=phone,
        email=email,
        product=product,
        quantity=qty_int,
        delivery_location=destination,
        notes=notes,
        status="new",
    )
    db.session.add(order)
    db.session.commit()
    return jsonify({"success": True}), 200


# ======================
# Admin: Contact Messages (ADMIN ONLY)
# ======================
@main.route("/admin/contact-messages")
@admin_required
def contact_messages():
    messages = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
    return render_template(
        "admin/contact_messages.html",
        messages=messages,
        current_year=datetime.utcnow().year,
    )


@main.route("/admin/contact-messages/<int:msg_id>/update-status", methods=["POST"])
@admin_required
def update_contact_status(msg_id):
    new_status = request.form.get("status")
    message = ContactMessage.query.get_or_404(msg_id)

    if new_status in ["new", "reviewed", "closed"]:
        message.status = new_status
        db.session.commit()
        flash("Message status updated.", "success")
    else:
        flash("Invalid status.", "error")

    return redirect(url_for("main.contact_messages"))

# ======================
# Admin: Order Requests (ADMIN ONLY)
# ======================
@main.route("/admin/order-requests", endpoint="order_requests")
@admin_required
def admin_order_requests():
    # Optional filter: /admin/order-requests?status=new
    qst = (request.args.get("status") or "").strip().lower()
    allowed = {"new", "reviewed", "approved", "rejected"}

    qry = OrderRequest.query
    if qst in allowed:
        qry = qry.filter(OrderRequest.status == qst)

    orders = qry.order_by(OrderRequest.created_at.desc()).all()

    return render_template(
        "admin/order_requests.html",
        orders=orders,
        current_year=datetime.utcnow().year,
    )


@main.route(
    "/admin/order-requests/<int:order_id>/status",
    methods=["POST"],
    endpoint="order_request_set_status",
)
@admin_required
def order_request_set_status(order_id):
    order = OrderRequest.query.get_or_404(order_id)

    new_status = (request.form.get("status") or "").strip().lower()
    allowed = {"new", "reviewed", "approved", "rejected"}

    if new_status not in allowed:
        flash("Invalid status.", "danger")
        return redirect(url_for("main.order_requests"))

    order.status = new_status
    db.session.commit()
    flash(f"Order #{order.id} marked as '{new_status}'.", "success")

    nxt = request.form.get("next")
    if nxt:
        return redirect(nxt)

    return redirect(url_for("main.order_requests"))


# ======================
# Animal Pipeline Views (ADMIN ONLY)
# ======================
@main.route("/animals/<animal_type>/<status>")
@admin_required
def animal_pipeline_view(animal_type, status):
    model_map = {"goat": Goat, "sheep": Sheep, "cattle": Cattle}

    if animal_type not in model_map:
        flash("Invalid animal type", "danger")
        return redirect(url_for("main.dashboard"))

    allowed_statuses = ["on_farm", "aggregated", "processing", "processed", "sold"]
    if status not in allowed_statuses:
        flash("Invalid status", "danger")
        return redirect(url_for("main.dashboard"))

    Model = model_map[animal_type]
    animals = Model.query.filter_by(status=status).order_by(Model.created_at.desc()).all()

    return render_template(
        "animals/pipeline_list.html",
        animals=animals,
        animal_type=animal_type,
        status=status,
        current_year=datetime.utcnow().year,
    )


def _get_processing_batch_or_404(batch_id: int) -> ProcessingBatch:
    return ProcessingBatch.query.get_or_404(batch_id)


def _animals_in_processing_batch(batch: ProcessingBatch):
    if batch.animal_type == "goat":
        return batch.goats
    if batch.animal_type == "sheep":
        return batch.sheep
    if batch.animal_type == "cattle":
        return batch.cattle
    return []


def generate_invoice_number() -> str:
    year = datetime.utcnow().year
    count = Invoice.query.count() + 1
    return f"RZ-INV-{year}-{count:04d}"


# ======================
# Processing Yield (ADMIN ONLY)
# ======================
@main.route("/processing/<int:batch_id>/yield", methods=["GET", "POST"])
@admin_required
def record_processing_yield(batch_id):
    batch = _get_processing_batch_or_404(batch_id)

    existing = ProcessingYield.query.filter_by(processing_batch_id=batch.id).first()
    if existing and request.method == "GET":
        flash("Yield already recorded for this batch.", "info")
        return redirect(url_for("main.view_invoiceable_batch", batch_id=batch.id))

    if request.method == "POST":
        total_carcass_weight_kg = _parse_float(request.form.get("total_carcass_weight_kg"))
        parts_included = request.form.get("parts_included_in_batch_sale") == "yes"
        parts_sold_separately = request.form.get("parts_sold_separately") == "yes"
        parts_notes = request.form.get("parts_notes")

        if total_carcass_weight_kg is None:
            flash("Total carcass weight is required.", "danger")
            return redirect(request.url)

        y = ProcessingYield(
            processing_batch_id=batch.id,
            total_carcass_weight_kg=total_carcass_weight_kg,
            parts_included_in_batch_sale=parts_included,
            parts_sold_separately=parts_sold_separately,
            parts_notes=parts_notes,
            recorded_by_user_id=current_user.id,
        )

        for animal in _animals_in_processing_batch(batch):
            if (animal.status or "").strip() == "processing":
                animal.status = "processed"

        db.session.add(y)
        db.session.commit()

        flash("Processing yield recorded successfully.", "success")
        return redirect(url_for("main.view_invoiceable_batch", batch_id=batch.id))

    return render_template(
        "processing/yield_add.html",
        batch=batch,
        current_year=datetime.utcnow().year,
    )


# ======================
# Processing Sale (ADMIN ONLY) + Friendly duplicate handling
# ======================
@main.route("/processing/<int:batch_id>/sale", methods=["GET", "POST"])
@admin_required
def record_processing_batch_sale(batch_id):
    batch = _get_processing_batch_or_404(batch_id)

    y = ProcessingYield.query.filter_by(processing_batch_id=batch.id).first()
    if not y:
        flash("Record processing yield first before selling the batch.", "danger")
        return redirect(url_for("main.record_processing_yield", batch_id=batch.id))

    existing_sale = ProcessingBatchSale.query.filter_by(processing_batch_id=batch.id).first()
    if existing_sale and request.method == "GET":
        flash("Sale already recorded for this batch.", "info")
        return redirect(url_for("main.generate_invoice_from_sale", sale_id=existing_sale.id))

    buyers = Buyer.query.order_by(Buyer.name.asc()).all()

    if request.method == "POST":
        # back-button / double-submit protection
        existing_sale = ProcessingBatchSale.query.filter_by(processing_batch_id=batch.id).first()
        if existing_sale:
            flash("Sale already recorded for this batch. You can view the invoice.", "info")
            return redirect(url_for("main.generate_invoice_from_sale", sale_id=existing_sale.id))

        buyer_id = _parse_int(request.form.get("buyer_id"))
        buyer_name = request.form.get("buyer_name")
        buyer_phone = request.form.get("buyer_phone")
        buyer_email = request.form.get("buyer_email")
        total_sale_price = _parse_float(request.form.get("total_sale_price"))
        sale_date = _parse_date(request.form.get("sale_date"))
        notes = request.form.get("notes")

        if total_sale_price is None:
            flash("Total sale price is required.", "danger")
            return redirect(request.url)

        if buyer_id:
            buyer = Buyer.query.get(buyer_id)
            if not buyer:
                flash("Selected buyer not found.", "danger")
                return redirect(request.url)
        else:
            if not buyer_name:
                flash("Provide buyer name or select an existing buyer.", "danger")
                return redirect(request.url)
            buyer = Buyer(name=buyer_name.strip(), phone=buyer_phone, email=buyer_email)
            db.session.add(buyer)
            db.session.flush()

        sale = ProcessingBatchSale(
            processing_batch_id=batch.id,
            buyer_id=buyer.id,
            total_sale_price=total_sale_price,
            sale_date=sale_date or date.today(),
            notes=notes,
            recorded_by_user_id=current_user.id,
        )

        for animal in _animals_in_processing_batch(batch):
            if (animal.status or "").strip() in ("processed", "processing"):
                animal.status = "sold"

        db.session.add(sale)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            existing_sale = ProcessingBatchSale.query.filter_by(processing_batch_id=batch.id).first()
            flash("Sale already recorded for this batch. You can view the invoice.", "info")
            if existing_sale:
                return redirect(url_for("main.generate_invoice_from_sale", sale_id=existing_sale.id))
            return redirect(url_for("main.view_invoiceable_batch", batch_id=batch.id))

        flash("Batch sale recorded. You can now generate the invoice.", "success")
        return redirect(url_for("main.generate_invoice_from_sale", sale_id=sale.id))

    return render_template(
        "sales/batch_sale_add.html",
        batch=batch,
        yield_record=y,
        buyers=buyers,
        current_year=datetime.utcnow().year,
    )


# ======================
# Invoice generation + view (ADMIN ONLY)
# ======================
@main.route("/sales/<int:sale_id>/invoice/generate", methods=["GET"])
@admin_required
def generate_invoice_from_sale(sale_id):
    sale = ProcessingBatchSale.query.get_or_404(sale_id)
    batch = ProcessingBatch.query.get_or_404(sale.processing_batch_id)
    y = ProcessingYield.query.filter_by(processing_batch_id=batch.id).first()

    existing_invoice = Invoice.query.filter_by(processing_batch_sale_id=sale.id).first()
    if existing_invoice:
        flash("Invoice already exists for this sale.", "info")
        return redirect(url_for("main.view_invoice", invoice_id=existing_invoice.id))

    invoice_number = generate_invoice_number()

    inv = Invoice(
        invoice_number=invoice_number,
        buyer_id=sale.buyer_id,
        processing_batch_sale_id=sale.id,
        issue_date=date.today(),
        status=InvoiceStatus.ISSUED,       # ✅ Enum (NO strings)
        issued_at=datetime.utcnow(),       # ✅ timestamp
        subtotal=float(sale.total_sale_price),
        tax=0.0,
        total=float(sale.total_sale_price),
        notes=sale.notes,
        terms="Payment due as agreed.",
        issued_by_user_id=current_user.id,
    )

    carcass_info = ""
    if y:
        carcass_info = f" | Carcass weight: {y.total_carcass_weight_kg} kg"
        if y.parts_notes:
            carcass_info += f" | Parts: {y.parts_notes}"

    item = InvoiceItem(
        description=f"Processing Batch #{batch.id} ({batch.animal_type}) - 1 lot{carcass_info}",
        quantity=1.0,
        unit_price=float(sale.total_sale_price),
        line_total=float(sale.total_sale_price),
    )

    db.session.add(inv)
    db.session.flush()
    item.invoice_id = inv.id
    db.session.add(item)
    db.session.commit()

    flash("Invoice generated successfully.", "success")
    return redirect(url_for("main.view_invoice", invoice_id=inv.id))


@main.route("/invoices/<int:invoice_id>")
@admin_required
def view_invoice(invoice_id):
    inv = Invoice.query.get_or_404(invoice_id)
    buyer = Buyer.query.get_or_404(inv.buyer_id)
    items = InvoiceItem.query.filter_by(invoice_id=inv.id).all()

    sale = ProcessingBatchSale.query.get_or_404(inv.processing_batch_sale_id)
    batch = ProcessingBatch.query.get_or_404(sale.processing_batch_id)
    y = ProcessingYield.query.filter_by(processing_batch_id=batch.id).first()

    return render_template(
        "invoices/invoice_view.html",
        invoice=inv,
        buyer=buyer,
        items=items,
        sale=sale,
        batch=batch,
        yield_record=y,
        current_year=datetime.utcnow().year,
        invoice_status_value=_safe_enum_value(inv.status),
    )


# ======================
# Invoice PDF (ADMIN) — no DB writes
# ======================
@main.route("/invoices/<int:invoice_id>/pdf", methods=["GET"])
@login_required
@admin_required
def invoice_pdf(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)

    pdf_bytes = render_invoice_pdf(invoice)
    filename = f"Rizara_Invoice_{invoice.invoice_number or invoice.id}.pdf"

    return current_app.response_class(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ======================
# Processing Batch Overview (ADMIN ONLY)
# ======================
@main.route("/processing/<int:batch_id>/overview")
@admin_required
def view_invoiceable_batch(batch_id):
    batch = _get_processing_batch_or_404(batch_id)
    y = ProcessingYield.query.filter_by(processing_batch_id=batch.id).first()
    sale = ProcessingBatchSale.query.filter_by(processing_batch_id=batch.id).first()
    invoice = Invoice.query.filter_by(processing_batch_sale_id=sale.id).first() if sale else None

    return render_template(
        "processing/batch_overview.html",
        batch=batch,
        yield_record=y,
        sale=sale,
        invoice=invoice,
        current_year=datetime.utcnow().year,
    )


# =========================================================
# BUYER PORTAL
# =========================================================
@main.route("/buyer/dashboard")
@buyer_required
def buyer_dashboard():
    buyer = Buyer.query.filter_by(user_id=current_user.id).first()
    if not buyer:
        flash("Buyer profile not linked to this account. Please contact Rizara support.", "danger")
        return redirect(url_for("auth.logout"))

    sales = (
        ProcessingBatchSale.query.filter_by(buyer_id=buyer.id)
        .order_by(ProcessingBatchSale.sale_date.desc())
        .all()
    )

    invoice_map = {}
    if sales:
        sale_ids = [s.id for s in sales]
        invoices = Invoice.query.filter(Invoice.processing_batch_sale_id.in_(sale_ids)).all()
        invoice_map = {inv.processing_batch_sale_id: inv for inv in invoices}

    return render_template(
        "buyer/dashboard.html",
        buyer=buyer,
        sales=sales,
        invoice_map=invoice_map,
        current_year=datetime.utcnow().year,
    )


@main.route("/buyer/invoices/<int:invoice_id>")
@buyer_required
def buyer_view_invoice(invoice_id):
    buyer = Buyer.query.filter_by(user_id=current_user.id).first()
    if not buyer:
        flash("Buyer profile not linked to this account.", "danger")
        return redirect(url_for("auth.logout"))

    inv = Invoice.query.get_or_404(invoice_id)
    if inv.buyer_id != buyer.id:
        flash("You do not have access to that invoice.", "danger")
        return redirect(url_for("main.buyer_dashboard"))

    items = InvoiceItem.query.filter_by(invoice_id=inv.id).all()
    sale = ProcessingBatchSale.query.get_or_404(inv.processing_batch_sale_id)
    batch = ProcessingBatch.query.get_or_404(sale.processing_batch_id)
    y = ProcessingYield.query.filter_by(processing_batch_id=batch.id).first()

    return render_template(
        "buyer/invoice_view.html",
        invoice=inv,
        buyer=buyer,
        items=items,
        sale=sale,
        batch=batch,
        yield_record=y,
        current_year=datetime.utcnow().year,
        invoice_status_value=_safe_enum_value(inv.status),
    )


@main.route("/buyer/invoices/<int:invoice_id>/pdf", methods=["GET"])
@buyer_required
def buyer_invoice_pdf(invoice_id):
    buyer = Buyer.query.filter_by(user_id=current_user.id).first()
    if not buyer:
        flash("Buyer profile not linked to this account.", "danger")
        return redirect(url_for("auth.logout"))

    inv = Invoice.query.get_or_404(invoice_id)
    if inv.buyer_id != buyer.id:
        flash("You do not have access to that invoice.", "danger")
        return redirect(url_for("main.buyer_dashboard"))

    pdf_bytes = render_invoice_pdf(inv)
    filename = f"Rizara_Invoice_{inv.invoice_number or inv.id}.pdf"

    return current_app.response_class(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@main.route("/buyer/orders/new", methods=["GET", "POST"])
@buyer_required
def buyer_new_order():
    buyer = Buyer.query.filter_by(user_id=current_user.id).first()
    if not buyer:
        flash("Buyer profile not linked to this account.", "danger")
        return redirect(url_for("auth.logout"))

    if request.method == "POST":
        product = (request.form.get("product") or "").strip()
        quantity = _parse_int(request.form.get("quantity"))
        delivery_location = (request.form.get("delivery_location") or "").strip()
        notes = request.form.get("notes")

        if not product or not quantity or not delivery_location:
            flash("Product, quantity and delivery location are required.", "danger")
            return redirect(request.url)

        order = OrderRequest(
            buyer_name=buyer.name,
            phone=buyer.phone or "",
            email=buyer.email,
            product=product,
            quantity=quantity,
            delivery_location=delivery_location,
            notes=notes,
            status="new",
            # If you later add OrderRequest.buyer_id in models.py, set it:
            # buyer_id=buyer.id,
        )
        db.session.add(order)
        db.session.commit()

        flash("Order submitted successfully.", "success")
        return redirect(url_for("main.buyer_dashboard"))

    return render_template(
        "buyer/order_new.html",
        buyer=buyer,
        current_year=datetime.utcnow().year,
    )
