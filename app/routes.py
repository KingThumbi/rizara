# app/routes.py
from __future__ import annotations

import os
import uuid
from functools import wraps
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import requests
import sqlalchemy as sa
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    Response,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import lazyload
from werkzeug.exceptions import NotFound

from app.extensions import db, limiter
from app.utils.guards import admin_required
from app.utils.invoice_pdf import render_invoice_pdf

from app.models import (
    AggregationBatch,
    Buyer,
    Cattle,
    ContactMessage,
    Document,
    DocumentSignature,
    Farmer,
    Goat,
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    OrderRequest,
    ProcessingBatch,
    ProcessingBatchSale,
    ProcessingYield,
    Sheep,
    User,
)

from app.services.document_files import (
    store_document_pdf_snapshot,
    load_document_snapshot_bytes,
)
from app.services.document_renderer import render_export_sales_contract_pdf_bytes

main = Blueprint("main", __name__)

#base_url helper
def _public_base_url() -> str:
    """
    Base URL used by PDF rendering for absolute links (assets, images, etc).
    Priority:
      1) PUBLIC_BASE_URL config/env (recommended in production)
      2) request.url_root in runtime (good locally)
    """
    cfg = (current_app.config.get("PUBLIC_BASE_URL") or os.getenv("PUBLIC_BASE_URL") or "").strip()
    if cfg:
        return cfg.rstrip("/")
    # request.url_root ends with trailing slash
    if request and request.url_root:
        return request.url_root.rstrip("/")
    return "http://127.0.0.1:5000"

def _weasy_base_url() -> str:
    """
    WeasyPrint base_url:
    - must be an absolute URL so relative static/assets resolve.
    - request.url_root includes trailing slash.
    """
    return (request.url_root or "").rstrip("/") + "/"   

# =========================================================
# Time helpers (STANDARD)
# =========================================================
def utcnow_naive() -> datetime:
    """Naive UTC now (preferred for DB timestamp without timezone)."""
    return datetime.utcnow()


def utcnow_aware() -> datetime:
    """Aware UTC now (rarely stored; mostly for comparisons)."""
    return datetime.now(timezone.utc)


def _is_expired(exp, now_utc_aware: datetime, now_utc_naive: datetime) -> bool:
    """
    exp can be naive or aware depending on DB column history.
    Compare safely without crashing.
    """
    if not exp:
        return True
    try:
        if getattr(exp, "tzinfo", None) is None:
            return now_utc_naive > exp
        return now_utc_aware > exp
    except Exception:
        return True


def _real_ip() -> str:
    xff = (request.headers.get("X-Forwarded-For") or "").strip()
    if xff:
        return xff.split(",")[0].strip() or "0.0.0.0"
    return request.remote_addr or "0.0.0.0"


def _safe_user_agent(maxlen: int = 255) -> str:
    ua = (request.headers.get("User-Agent") or "").strip()
    return (ua[:maxlen] if ua else "unknown")


# =========================================================
# Small DB helper (SAFE)
# =========================================================
def _commit_or_rollback(action: str) -> bool:
    try:
        db.session.commit()
        return True
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("%s failed", action)
        flash(f"{action} failed. Please try again.", "danger")
        return False


# ======================
# Buyer Guard (PORTAL)
# ======================
def buyer_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if (getattr(current_user, "role", "") or "").strip().lower() != "buyer":
            flash("Access denied.", "danger")
            return redirect(url_for("main.dashboard"))
        return view(*args, **kwargs)

    return wrapped


def _get_buyer_for_current_user_or_redirect():
    buyer = Buyer.query.filter_by(user_id=current_user.id).first()
    if not buyer:
        flash("Buyer profile not linked to this account. Contact Rizara support/admin.", "danger")
        return None, redirect(url_for("auth.logout"))
    return buyer, None


# ======================
# Role Helpers
# ======================
def _role() -> str:
    return (getattr(current_user, "role", "") or "").strip().lower()


def _is_admin() -> bool:
    role = _role()
    return bool(getattr(current_user, "is_admin", False)) or role in ("admin", "super_admin", "superadmin")


# ======================
# Parsers
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
    try:
        return v.value
    except Exception:
        return v


# ======================
# reCAPTCHA Verification (SECURE)
# ======================
def verify_recaptcha(response_token: str) -> bool:
    secret = (current_app.config.get("RECAPTCHA_SECRET_KEY") if current_app else None) or os.getenv("RECAPTCHA_SECRET_KEY")

    # Fail closed if not configured
    if not secret or not response_token:
        current_app.logger.warning("reCAPTCHA missing secret/token; rejecting.")
        return False

    try:
        r = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={"secret": secret, "response": response_token},
            timeout=5,
        )
        return bool(r.json().get("success", False))
    except Exception:
        current_app.logger.exception("reCAPTCHA verification failed.")
        return False

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
    try:
        return v.value
    except Exception:
        return v


# ======================
# reCAPTCHA Verification (SECURE)
# ======================
def verify_recaptcha(response_token: str) -> bool:
    """
    Used to prevent spam in public forms (contact + order).
    IMPORTANT:
    - Do NOT hardcode the secret key in code.
    - Set RECAPTCHA_SECRET_KEY in environment variables (Render + local).
    """
    secret = (current_app.config.get("RECAPTCHA_SECRET_KEY") if current_app else None) or os.getenv(
        "RECAPTCHA_SECRET_KEY"
    )

    # Fail closed if not configured
    if not secret or not response_token:
        if current_app:
            current_app.logger.warning("reCAPTCHA secret/token missing; rejecting request.")
        return False

    try:
        r = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={"secret": secret, "response": response_token},
            timeout=5,
        )
        return bool(r.json().get("success", False))
    except Exception:
        if current_app:
            current_app.logger.exception("reCAPTCHA verification failed.")
        return False


# =========================================================
# Dashboard Router (ROLE-SAFE LANDING)
# =========================================================
@main.route("/dashboard")
@login_required
def dashboard():
    """
    Role-safe landing endpoint.
    Newly created users must never get a 403 here — they are routed to a permitted dashboard.
    """
    role = _role()

    if _is_admin():
        return redirect(url_for("main.admin_dashboard"))

    if role == "buyer":
        return redirect(url_for("main.buyer_dashboard"))

    if role == "farmer":
        return redirect(url_for("main.farmer_dashboard"))
    if role in ("staff", "rizara_staff", "operations"):
        return redirect(url_for("main.staff_dashboard"))
    if role == "transporter":
        return redirect(url_for("main.transporter_dashboard"))
    if role in ("service_provider", "veterinary", "agronomist", "feed_specialist"):
        return redirect(url_for("main.service_provider_dashboard"))

    # Unknown role -> safe default
    return redirect(url_for("main.buyer_dashboard"))


# =========================================================
# Admin Operations Dashboard (ADMIN ONLY)
# =========================================================
@main.route("/admin/dashboard")
@admin_required
def admin_dashboard():
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

    stats["latest_contacts"] = ContactMessage.query.order_by(ContactMessage.created_at.desc()).limit(5).all()
    stats["latest_orders"] = OrderRequest.query.order_by(OrderRequest.created_at.desc()).limit(5).all()

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        goat_pipeline=stats.get("goat_pipeline", {}),
        sheep_pipeline=stats.get("sheep_pipeline", {}),
        cattle_pipeline=stats.get("cattle_pipeline", {}),
        current_year=datetime.utcnow().year,
    )


# =========================================================
# Role Dashboards (NON-ADMIN)
# =========================================================
@main.route("/farmer/dashboard")
@login_required
def farmer_dashboard():
    if _role() != "farmer":
        flash("Access denied.", "danger")
        return redirect(url_for("main.dashboard"))
    return render_template("farmers/dashboard.html", current_year=datetime.utcnow().year)


@main.route("/staff/dashboard")
@login_required
def staff_dashboard():
    if _role() not in ("staff", "rizara_staff", "operations"):
        flash("Access denied.", "danger")
        return redirect(url_for("main.dashboard"))
    return render_template("staff/dashboard.html", current_year=datetime.utcnow().year)


@main.route("/transporter/dashboard")
@login_required
def transporter_dashboard():
    if _role() != "transporter":
        flash("Access denied.", "danger")
        return redirect(url_for("main.dashboard"))
    return render_template("transporter/dashboard.html", current_year=datetime.utcnow().year)


@main.route("/service-provider/dashboard")
@login_required
def service_provider_dashboard():
    if _role() not in ("service_provider", "veterinary", "agronomist", "feed_specialist"):
        flash("Access denied.", "danger")
        return redirect(url_for("main.dashboard"))
    return render_template("service_provider/dashboard.html", current_year=datetime.utcnow().year)


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
        if not _commit_or_rollback("Add farmer"):
            return redirect(request.url)
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
        if not _commit_or_rollback("Register goat"):
            return redirect(request.url)
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
        if not _commit_or_rollback("Register sheep"):
            return redirect(request.url)
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
        if not _commit_or_rollback("Register cattle"):
            return redirect(request.url)
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
                animal.aggregated_at = datetime.utcnow()  # keep consistent with existing schema
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

            if not _commit_or_rollback(f"Create {label} aggregation batch"):
                return redirect(request.url)

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
        available_animals = Model.query.filter(Model.status == "aggregated").order_by(Model.created_at.desc()).all()

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
            if not _commit_or_rollback(f"Create {label} processing batch"):
                return redirect(request.url)

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
    # Honeypot
    if request.form.get("hp_field"):
        return jsonify({"success": False}), 200

    if not verify_recaptcha(request.form.get("g-recaptcha-response")):
        return jsonify({"success": False, "error": "recaptcha_failed"}), 403

    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    message = (request.form.get("message") or "").strip()

    if not name or not email or not message:
        return jsonify({"success": False}), 400

    contact = ContactMessage(
        name=name,
        email=email,
        subject=f"Website contact form - {phone}" if phone else "Website contact form",
        message=message,
        status="new",
    )
    db.session.add(contact)
    if not _commit_or_rollback("Submit contact"):
        return jsonify({"success": False}), 500
    return jsonify({"success": True}), 200


@main.route("/submit-order", methods=["POST"])
@limiter.limit("3 per minute")
def submit_order():
    # Honeypot
    if request.form.get("hp_field"):
        return jsonify({"success": False}), 200

    if not verify_recaptcha(request.form.get("g-recaptcha-response")):
        return jsonify({"success": False, "error": "recaptcha_failed"}), 403

    buyer_name = (request.form.get("buyerName") or "").strip()
    email = (request.form.get("email") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    product = (request.form.get("product") or "").strip()
    quantity = request.form.get("quantity")
    destination = (request.form.get("destination") or "").strip()
    notes = (request.form.get("message") or "").strip() or None

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
    if not _commit_or_rollback("Submit order"):
        return jsonify({"success": False}), 500
    return jsonify({"success": True}), 200

def _real_ip() -> str:
    xff = (request.headers.get("X-Forwarded-For") or "").strip()
    if xff:
        return xff.split(",")[0].strip() or "0.0.0.0"
    return request.remote_addr or "0.0.0.0"


def _safe_user_agent(maxlen: int = 255) -> str:
    ua = (request.headers.get("User-Agent") or "").strip()
    return (ua[:maxlen] if ua else "unknown")


def _is_expired(exp, now_utc_aware: datetime, now_utc_naive: datetime) -> bool:
    """
    exp can be naive or aware depending on DB column history.
    Compare safely without crashing.
    """
    if not exp:
        return True
    try:
        if getattr(exp, "tzinfo", None) is None:
            return now_utc_naive > exp
        return now_utc_aware > exp
    except Exception:
        return True


@main.route("/sign/<token>", methods=["GET"], endpoint="sign_document_get")
def sign_document_get(token: str):
    token = (token or "").strip()
    if not token:
        raise NotFound()

    doc = (
        db.session.query(Document)
        .options(lazyload("*"))
        .filter(Document.buyer_sign_token == token)
        .first()
    )
    if not doc:
        raise NotFound()

    if doc.status in ("buyer_signed", "executed", "void"):
        return render_template("public/sign_already_done.html", document=doc), 409

    now_aware = utcnow_aware()
    now_naive = utcnow_naive()
    if _is_expired(doc.buyer_sign_token_expires_at, now_aware, now_naive):
        return render_template("public/sign_expired.html"), 410

    if doc.doc_type == "export_sales_contract":
        now_eat = datetime.now(ZoneInfo("Africa/Nairobi"))
        return render_template(
            "public/sign_export_sales_contract.html",
            document=doc,
            token=token,
            now_eat=now_eat,
        )

    return render_template(
        "public/sign_document.html",
        document=doc,
        token=token,
        errors=[],
        full_name="",
        email="",
    )


@main.route("/sign/<token>", methods=["POST"], endpoint="sign_document_post")
def sign_document_post(token: str):
    token = (token or "").strip()
    if not token:
        raise NotFound()

    # Accept BOTH form styles:
    # Generic template: full_name/email/accept
    # Export contract: signer_name/signer_email/consent
    signer_name = ((request.form.get("signer_name") or "").strip() or (request.form.get("full_name") or "").strip())
    signer_email_raw = (
        (request.form.get("signer_email") or "").strip().lower()
        or (request.form.get("email") or "").strip().lower()
        or ""
    )
    consent_raw = (request.form.get("consent") or request.form.get("accept") or "").strip().lower()

    ip = _real_ip()
    ua = _safe_user_agent(255)

    now_aware = utcnow_aware()
    now_naive = utcnow_naive()

    errors: list[str] = []
    if len(signer_name) < 2:
        errors.append("Please enter your full name.")
    if consent_raw not in ("yes", "on", "true", "1"):
        errors.append("You must confirm you agree to the terms before signing.")

    try:
        with db.session.begin_nested():
            # Lock doc row to prevent double-sign
            doc = (
                db.session.query(Document)
                .options(lazyload("*"))
                .filter(Document.buyer_sign_token == token)
                .with_for_update(of=Document)
                .first()
            )
            if not doc:
                raise NotFound()

            if doc.status in ("buyer_signed", "executed", "void"):
                return render_template("public/sign_already_done.html", document=doc), 409

            if _is_expired(doc.buyer_sign_token_expires_at, now_aware, now_naive):
                return render_template("public/sign_expired.html"), 410

            # Email rules:
            # - export_sales_contract allows optional email
            # - all other docs require valid email
            if doc.doc_type != "export_sales_contract":
                if not signer_email_raw or ("@" not in signer_email_raw or "." not in signer_email_raw):
                    errors.append("Please enter a valid email address.")

            if errors:
                if doc.doc_type == "export_sales_contract":
                    now_eat = datetime.now(ZoneInfo("Africa/Nairobi"))
                    for e in errors:
                        flash(e, "danger")
                    return render_template(
                        "public/sign_export_sales_contract.html",
                        document=doc,
                        token=token,
                        now_eat=now_eat,
                    ), 400

                return render_template(
                    "public/sign_document.html",
                    document=doc,
                    token=token,
                    errors=errors,
                    full_name=signer_name,
                    email=signer_email_raw,
                ), 400

            # Prevent duplicate signature insert
            existing_sig = (
                db.session.query(DocumentSignature)
                .filter(
                    DocumentSignature.document_id == doc.id,
                    DocumentSignature.signer_type == "buyer",
                )
                .first()
            )
            if existing_sig:
                return render_template("public/sign_already_done.html", document=doc), 409

            # Guarantee NOT NULL fields
            signer_email = signer_email_raw if signer_email_raw else "unknown@example.com"

            sig = DocumentSignature(
                document_id=doc.id,
                signer_type="buyer",
                signed_by_user_id=None,
                sign_method="typed",
                signer_name=signer_name,
                signer_email=signer_email,
                typed_consent_text="I confirm I have read and agree to the terms.",
                signed_at=now_naive,  # naive UTC stored
                ip_address=ip,
                user_agent=ua,
            )
            db.session.add(sig)

            # Stamp doc (always)
            doc.status = "buyer_signed"
            doc.buyer_signed_at = now_naive
            doc.buyer_sign_name = signer_name
            doc.buyer_sign_email = signer_email
            doc.buyer_sign_ip = ip
            doc.buyer_sign_user_agent = ua

            # Snapshot ONLY for export_sales_contract
            if doc.doc_type == "export_sales_contract":
                pdf_bytes = render_export_sales_contract_pdf_bytes(doc, base_url=_public_base_url())
                store_document_pdf_snapshot(doc, pdf_bytes=pdf_bytes, commit=False)

            # Revoke token
            doc.buyer_sign_token = None
            doc.buyer_sign_token_expires_at = None

            db.session.add(doc)

        db.session.commit()
        return render_template("public/sign_success.html", document=doc), 200

    except NotFound:
        raise

    except IntegrityError:
        db.session.rollback()
        return render_template("public/sign_already_done.html", document=None), 409

    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Buyer signing failed (SQLAlchemyError)")
        return render_template("public/sign_not_supported.html"), 500
    
# ======================
# Admin: Contact Messages (ADMIN ONLY)
# ======================
@main.route("/admin/contact-messages")
@admin_required
def contact_messages():
    messages = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
    return render_template("admin/contact_messages.html", messages=messages, current_year=datetime.utcnow().year)


@main.route("/admin/contact-messages/<int:msg_id>/update-status", methods=["POST"])
@admin_required
def update_contact_status(msg_id):
    new_status = (request.form.get("status") or "").strip().lower()
    message = ContactMessage.query.get_or_404(msg_id)

    if new_status in {"new", "reviewed", "closed"}:
        message.status = new_status
        if _commit_or_rollback("Update contact message status"):
            flash("Message status updated.", "success")
    else:
        flash("Invalid status.", "danger")

    return redirect(url_for("main.contact_messages"))


# ======================
# Admin: Order Requests (ADMIN ONLY)
# ======================
@main.route("/admin/order-requests", endpoint="order_requests")
@admin_required
def admin_order_requests():
    qst = (request.args.get("status") or "").strip().lower()
    allowed = {"new", "reviewed", "approved", "rejected"}

    qry = OrderRequest.query
    if qst in allowed:
        qry = qry.filter(OrderRequest.status == qst)

    orders = qry.order_by(OrderRequest.created_at.desc()).all()
    return render_template("admin/order_requests.html", orders=orders, current_year=datetime.utcnow().year)


@main.route("/admin/order-requests/<int:order_id>/status", methods=["POST"], endpoint="order_request_set_status")
@admin_required
def order_request_set_status(order_id):
    order = OrderRequest.query.get_or_404(order_id)

    new_status = (request.form.get("status") or "").strip().lower()
    allowed = {"new", "reviewed", "approved", "rejected"}

    if new_status not in allowed:
        flash("Invalid status.", "danger")
        return redirect(url_for("main.order_requests"))

    order.status = new_status
    if _commit_or_rollback("Update order status"):
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

    allowed_statuses = {"on_farm", "aggregated", "processing", "processed", "sold"}
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
    """
    Generates a human-friendly invoice number.
    Note: This is not perfectly concurrency-safe if two invoices are created at the same instant.
    If you expect high concurrency, we can switch to a DB sequence-based counter.
    """
    year = datetime.utcnow().year
    count = (db.session.query(sa.func.count(Invoice.id)).scalar() or 0) + 1
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
        if not _commit_or_rollback("Record processing yield"):
            return redirect(request.url)

        flash("Processing yield recorded successfully.", "success")
        return redirect(url_for("main.view_invoiceable_batch", batch_id=batch.id))

    return render_template("processing/yield_add.html", batch=batch, current_year=datetime.utcnow().year)


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
        # Re-check in POST for race conditions / double submits
        existing_sale = ProcessingBatchSale.query.filter_by(processing_batch_id=batch.id).first()
        if existing_sale:
            flash("Sale already recorded for this batch. You can view the invoice.", "info")
            return redirect(url_for("main.generate_invoice_from_sale", sale_id=existing_sale.id))

        buyer_id = _parse_int(request.form.get("buyer_id"))
        buyer_name = (request.form.get("buyer_name") or "").strip() or None
        buyer_phone = (request.form.get("buyer_phone") or "").strip() or None
        buyer_email = (request.form.get("buyer_email") or "").strip() or None
        total_sale_price = _parse_float(request.form.get("total_sale_price"))
        sale_date = _parse_date(request.form.get("sale_date"))
        notes = (request.form.get("notes") or "").strip() or None

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
            buyer = Buyer(name=buyer_name, phone=buyer_phone, email=buyer_email)
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

    # If invoice_number uniqueness ever clashes, we retry once.
    for attempt in range(2):
        invoice_number = generate_invoice_number()

        inv = Invoice(
            invoice_number=invoice_number,
            buyer_id=sale.buyer_id,
            processing_batch_sale_id=sale.id,
            issue_date=date.today(),
            status=InvoiceStatus.ISSUED,  # Enum
            issued_at=datetime.utcnow(),
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

        try:
            db.session.commit()
            flash("Invoice generated successfully.", "success")
            return redirect(url_for("main.view_invoice", invoice_id=inv.id))
        except IntegrityError:
            db.session.rollback()
            if attempt == 0:
                continue
            flash("Invoice generation failed due to a numbering conflict. Try again.", "danger")
            return redirect(url_for("main.view_invoiceable_batch", batch_id=batch.id))

    flash("Invoice generation failed.", "danger")
    return redirect(url_for("main.view_invoiceable_batch", batch_id=batch.id))


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
    buyer, resp = _get_buyer_for_current_user_or_redirect()
    if resp:
        return resp

    sales = ProcessingBatchSale.query.filter_by(buyer_id=buyer.id).order_by(ProcessingBatchSale.sale_date.desc()).all()

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
    buyer, resp = _get_buyer_for_current_user_or_redirect()
    if resp:
        return resp

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
    buyer, resp = _get_buyer_for_current_user_or_redirect()
    if resp:
        return resp

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
    buyer, resp = _get_buyer_for_current_user_or_redirect()
    if resp:
        return resp

    if request.method == "POST":
        product = (request.form.get("product") or "").strip()
        quantity = _parse_int(request.form.get("quantity"))
        delivery_location = (request.form.get("delivery_location") or "").strip()
        notes = (request.form.get("notes") or "").strip() or None

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
        )
        db.session.add(order)
        if not _commit_or_rollback("Submit buyer order"):
            return redirect(request.url)

        flash("Order submitted successfully.", "success")
        return redirect(url_for("main.buyer_dashboard"))

    return render_template("buyer/order_new.html", buyer=buyer, current_year=datetime.utcnow().year)

@main.route("/buyer/documents/<uuid:document_id>/signed.pdf", methods=["GET"])
@buyer_required
def buyer_download_signed_contract(document_id):
    buyer, resp = _get_buyer_for_current_user_or_redirect()
    if resp:
        return resp

    # Keep query light (avoid any model-level eager joins)
    doc = (
        db.session.query(Document)
        .options(lazyload("*"))
        .filter(Document.id == document_id)
        .first()
    )
    if not doc:
        abort(404)

    # Ensure buyer can only download their own doc
    if doc.buyer_id != buyer.id:
        abort(403)

    # Must be signed/executed and have a stored snapshot reference
    if doc.status not in ("buyer_signed", "executed"):
        abort(404)
    if not getattr(doc, "storage_key", None):
        abort(404)

    try:
        pdf_bytes = load_document_snapshot_bytes(doc.storage_key)
    except Exception:
        current_app.logger.exception(
            "Failed to load snapshot for document %s storage_key=%s",
            str(doc.id),
            str(doc.storage_key),
        )
        abort(404)

    # Safe filename (avoid spaces/special chars)
    doc_type = (doc.doc_type or "document").replace(" ", "_")
    version = (str(doc.version) if doc.version is not None else "1")
    filename = f"Rizara_{doc_type}_v{version}_SIGNED.pdf"

    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    # Prefer inline preview in-browser; change to 'attachment' if you want forced download
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp

@main.route("/admin/documents/<uuid:document_id>/contract.pdf", methods=["GET"])
@admin_required
def admin_download_contract_draft_pdf(document_id):
    doc = Document.query.get_or_404(document_id)

    if doc.doc_type != "export_sales_contract":
        flash("Draft PDF download is currently supported for Export Sales Contract only.", "warning")
        return redirect(url_for("main.admin_document_detail", document_id=document_id))

    pdf_bytes = render_export_sales_contract_pdf_bytes(doc, base_url=_weasy_base_url())
    filename = f"Rizara_Export_Sales_Contract_{doc.id}_v{doc.version}_DRAFT.pdf"

    return current_app.response_class(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )

@main.route("/sign/<token>/download", methods=["GET"])
def public_download_contract_draft_pdf(token: str):
    token = (token or "").strip()
    if not token:
        raise NotFound()

    doc = (
        db.session.query(Document)
        .options(lazyload("*"))
        .filter(Document.buyer_sign_token == token)
        .first()
    )
    if not doc:
        raise NotFound()

    # Only allow download for supported doc type
    if doc.doc_type != "export_sales_contract":
        return render_template("public/sign_not_supported.html"), 400

    # If token expired, you can still allow preview OR block it.
    # Since you want "just as LOI", we allow download as long as token exists.
    pdf_bytes = render_export_sales_contract_pdf_bytes(doc, base_url=_weasy_base_url())
    filename = f"Rizara_Export_Sales_Contract_{doc.id}_v{doc.version}_DRAFT.pdf"

    return current_app.response_class(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )        