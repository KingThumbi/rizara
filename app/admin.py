# app/admin.py
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from flask import Blueprint, flash, jsonify, make_response, redirect, render_template, request, url_for, abort, current_app, make_response
from flask_login import current_user
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified
from weasyprint import HTML
from werkzeug.security import generate_password_hash
from werkzeug.exceptions import NotFound

from zoneinfo import ZoneInfo

from .constants.roles import ROLES
from app.extensions import db
from app.models import Buyer, Document, DocumentSignature, User
from .utils.auth import allowed_roles_for
from .utils.guards import admin_required

from app.services.document_files import (
    load_document_snapshot_bytes,
    render_export_sales_contract_pdf_bytes,
    store_document_pdf_snapshot
)

from app.services.documents_scaffold import (
    DOC_TYPE_OPTIONS,
    DOC_TYPE_LOI,
    DOC_TYPE_EXPORT_SALES_CONTRACT,
    make_payload_scaffold,
    default_title_for,
    next_admin_url_for,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# -------------------------------------------------------------------
# Helpers / Constants
# -------------------------------------------------------------------
DOC_STATUSES = {"draft", "buyer_signed", "executed", "expired", "void"}
DOC_TYPE_MAXLEN = 50
DOC_TITLE_MAXLEN = 200
BUYER_NAME_MAXLEN = 160
BUYER_PHONE_MAXLEN = 30
BUYER_EMAIL_MAXLEN = 120
BUYER_ADDRESS_MAXLEN = 255
BUYER_TAXPIN_MAXLEN = 60


def _clean_str(value: str | None) -> str:
    return (value or "").strip()

def generate_buyer_sign_token(days_valid: int = 7):
    """
    Generates a buyer signing token and expiry timestamp.

    NOTE: Uses naive UTC because the DB column is naive (no tz).
    """
    token = secrets.token_urlsafe(32)
    expires_at = _utcnow_naive() + timedelta(days=days_valid)
    return token, expires_at

def _utcnow_naive() -> datetime:
    """DB columns are 'timestamp without time zone' so we store naive UTC."""
    return datetime.utcnow()


def _commit_or_rollback(action: str) -> bool:
    """Commit session; rollback + flash on failure. Returns True on success."""
    try:
        db.session.commit()
        return True
    except Exception as exc:
        db.session.rollback()
        flash(f"{action} failed: {exc}", "danger")
        return False


def _safe_filename(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s)
    return s[:120] or "document"

# -------------------------------------------------------------------
# Dashboard
# -------------------------------------------------------------------
@admin_bp.route("/", methods=["GET"])
@admin_required
def dashboard():
    return render_template("admin/dashboard.html")


# -------------------------------------------------------------------
# Roles API
# GET /admin/roles
# -------------------------------------------------------------------
@admin_bp.route("/roles", methods=["GET"])
@admin_required
def get_creatable_roles():
    allowed = allowed_roles_for(current_user)
    return (
        jsonify(
            {
                "current_role": getattr(current_user, "role", None),
                "allowed_roles": [{"key": r, "label": ROLES.get(r, r)} for r in allowed],
            }
        ),
        200,
    )


# -------------------------------------------------------------------
# Buyers (Customers)
# GET /admin/buyers
# GET+POST /admin/buyers/new
# -------------------------------------------------------------------
@admin_bp.route("/buyers", methods=["GET"])
@admin_required
def buyers_list():
    q = _clean_str(request.args.get("q"))
    query = Buyer.query

    if q:
        like = f"%{q}%"
        query = query.filter(
            sa.or_(
                Buyer.name.ilike(like),
                Buyer.email.ilike(like),
                Buyer.phone.ilike(like),
                Buyer.tax_pin.ilike(like),
            )
        )

    buyers = query.order_by(desc(Buyer.created_at)).limit(200).all()
    return render_template("admin/buyers_list.html", buyers=buyers, q=q)


@admin_bp.route("/buyers/new", methods=["GET", "POST"])
@admin_required
def buyers_new():
    if request.method == "GET":
        return render_template("admin/buyers_new.html")

    name = _clean_str(request.form.get("name"))
    email = _clean_str(request.form.get("email")).lower() or None
    phone = _clean_str(request.form.get("phone")) or None
    address = _clean_str(request.form.get("address")) or None
    tax_pin = _clean_str(request.form.get("tax_pin")) or None

    if not name:
        flash("Buyer name is required.", "danger")
        return render_template("admin/buyers_new.html")

    if len(name) > BUYER_NAME_MAXLEN:
        flash(f"Name too long (max {BUYER_NAME_MAXLEN}).", "danger")
        return render_template("admin/buyers_new.html")

    if email and len(email) > BUYER_EMAIL_MAXLEN:
        flash(f"Email too long (max {BUYER_EMAIL_MAXLEN}).", "danger")
        return render_template("admin/buyers_new.html")

    if phone and len(phone) > BUYER_PHONE_MAXLEN:
        flash(f"Phone too long (max {BUYER_PHONE_MAXLEN}).", "danger")
        return render_template("admin/buyers_new.html")

    if address and len(address) > BUYER_ADDRESS_MAXLEN:
        flash(f"Address too long (max {BUYER_ADDRESS_MAXLEN}).", "danger")
        return render_template("admin/buyers_new.html")

    if tax_pin and len(tax_pin) > BUYER_TAXPIN_MAXLEN:
        flash(f"Tax PIN too long (max {BUYER_TAXPIN_MAXLEN}).", "danger")
        return render_template("admin/buyers_new.html")

    # Optional: prevent duplicates by email (not DB-enforced on buyer.email).
    if email and Buyer.query.filter(sa.func.lower(Buyer.email) == email).first():
        flash("A buyer with that email already exists.", "danger")
        return render_template("admin/buyers_new.html")

    buyer = Buyer(
        name=name,
        email=email,
        phone=phone,
        address=address,
        tax_pin=tax_pin,
    )

    db.session.add(buyer)
    if not _commit_or_rollback("Create buyer"):
        return render_template("admin/buyers_new.html")

    flash("Buyer created.", "success")
    return redirect(url_for("admin.buyers_list"))


# -------------------------------------------------------------------
# Users (API)
# POST /admin/users  (JSON)
# -------------------------------------------------------------------
@admin_bp.route("/users", methods=["POST"])
@admin_required
def create_user_api():
    data = request.get_json(silent=True) or {}

    name = _clean_str(data.get("name"))
    email = _clean_str(data.get("email")).lower()
    phone = _clean_str(data.get("phone")) or None
    password = data.get("password")
    role = _clean_str(data.get("role"))

    if not name or not email or not password or not role:
        return jsonify({"error": "name, email, password and role are required"}), 400

    if role not in ROLES:
        return jsonify({"error": "Invalid role"}), 400

    if role not in allowed_roles_for(current_user):
        return jsonify({"error": "Not allowed to create this role"}), 403

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "User already exists"}), 409

    if phone and User.query.filter_by(phone=phone).first():
        return jsonify({"error": "Phone already exists"}), 409

    user = User(
        name=name,
        email=email,
        phone=phone,
        role=role,
        is_admin=role in ("admin", "super_admin"),
        password_hash=generate_password_hash(password),
    )

    db.session.add(user)
    if not _commit_or_rollback("Create user"):
        return jsonify({"error": "Failed to create user"}), 500

    return (
        jsonify(
            {
                "message": "User created successfully",
                "user": {"id": user.id, "email": user.email, "role": user.role},
            }
        ),
        201,
    )


# -------------------------------------------------------------------
# Users (Jinja)
# GET /admin/users
# GET+POST /admin/users/new
# -------------------------------------------------------------------
@admin_bp.route("/users", methods=["GET"])
@admin_required
def users_list():
    q = _clean_str(request.args.get("q"))

    query = User.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            sa.or_(
                User.name.ilike(like),
                User.email.ilike(like),
                User.phone.ilike(like),
                User.role.ilike(like),
            )
        )

    users = query.order_by(desc(User.id)).limit(200).all()
    return render_template("admin/users_list.html", users=users, q=q, ROLES=ROLES)


@admin_bp.route("/users/new", methods=["GET", "POST"])
@admin_required
def users_new():
    allowed = allowed_roles_for(current_user)
    role_options = [{"key": r, "label": ROLES.get(r, r)} for r in allowed]

    if request.method == "GET":
        return render_template("admin/users_new.html", role_options=role_options)

    name = _clean_str(request.form.get("name"))
    email = _clean_str(request.form.get("email")).lower()
    phone = _clean_str(request.form.get("phone")) or None
    password = request.form.get("password")
    role = _clean_str(request.form.get("role"))

    if not name or not email or not password or not role:
        flash("Name, email, password, and role are required.", "danger")
        return render_template("admin/users_new.html", role_options=role_options)

    if role not in ROLES:
        flash("Invalid role selected.", "danger")
        return render_template("admin/users_new.html", role_options=role_options)

    if role not in allowed:
        flash("Not allowed to create that role.", "danger")
        return render_template("admin/users_new.html", role_options=role_options)

    if User.query.filter_by(email=email).first():
        flash("Email already exists.", "danger")
        return render_template("admin/users_new.html", role_options=role_options)

    if phone and User.query.filter_by(phone=phone).first():
        flash("Phone already exists.", "danger")
        return render_template("admin/users_new.html", role_options=role_options)

    user = User(
        name=name,
        email=email,
        phone=phone,
        role=role,
        is_admin=role in ("admin", "super_admin"),
        password_hash=generate_password_hash(password),
    )

    db.session.add(user)
    if not _commit_or_rollback("Create user"):
        return render_template("admin/users_new.html", role_options=role_options)

    flash(f"User created: {user.email} ({user.role})", "success")
    return redirect(url_for("admin.users_list"))


# -------------------------------------------------------------------
# Documents (Jinja)
# GET /admin/documents
# GET+POST /admin/documents/new
# GET /admin/documents/<uuid>
# POST /admin/documents/<uuid>/status
# -------------------------------------------------------------------
@admin_bp.route("/documents", methods=["GET"])
@admin_required
def documents_list():
    q = _clean_str(request.args.get("q"))
    status = _clean_str(request.args.get("status"))
    doc_type = _clean_str(request.args.get("doc_type"))

    query = Document.query.join(Buyer, Document.buyer_id == Buyer.id)

    if q:
        like = f"%{q}%"
        query = query.filter(
            sa.or_(
                Buyer.name.ilike(like),
                Buyer.email.ilike(like),
                Buyer.phone.ilike(like),
                Document.title.ilike(like),
                sa.cast(Document.id, sa.String).ilike(like),
            )
        )

    if status:
        query = query.filter(Document.status == status)

    if doc_type:
        query = query.filter(Document.doc_type == doc_type)

    documents = query.order_by(desc(Document.created_at)).limit(200).all()

    return render_template(
        "admin/documents_list.html",
        documents=documents,
        q=q,
        status=status,
        doc_type=doc_type,
        doc_statuses=sorted(DOC_STATUSES),
    )

@admin_bp.route("/documents/new", methods=["GET", "POST"])
@admin_required
def documents_new():
    buyers = Buyer.query.order_by(Buyer.name.asc()).all()

    def _render_form(*, status_code: int = 200):
        return (
            render_template(
                "admin/documents_new.html",
                buyers=buyers,
                doc_statuses=sorted(DOC_STATUSES),
                doc_type_options=DOC_TYPE_OPTIONS,
                default_doc_type=DOC_TYPE_EXPORT_SALES_CONTRACT,
                default_version=1,
            ),
            status_code,
        )

    if request.method == "GET":
        return _render_form()

    # --- POST ---
    buyer_id = request.form.get("buyer_id", type=int)
    doc_type = (_clean_str(request.form.get("doc_type")) or "").lower()
    title = _clean_str(request.form.get("title"))
    version = request.form.get("version", type=int) or 1
    status = _clean_str(request.form.get("status") or "draft") or "draft"

    # Debug-friendly safety (remove later if you want)
    if buyer_id is None:
        flash("Buyer is required (buyer_id missing from form submission).", "danger")
        return _render_form(400)

    buyer = Buyer.query.get(buyer_id)
    if not buyer:
        flash("Buyer not found.", "danger")
        return _render_form(404)

    allowed_doc_types = {k for k, _label in DOC_TYPE_OPTIONS}
    if not doc_type:
        flash("Document type is required.", "danger")
        return _render_form(400)

    if doc_type not in allowed_doc_types:
        flash("Invalid document type selected.", "danger")
        return _render_form(400)

    if len(doc_type) > DOC_TYPE_MAXLEN:
        flash(f"Document type too long (max {DOC_TYPE_MAXLEN}).", "danger")
        return _render_form(400)

    if not title:
        title = default_title_for(doc_type)

    if len(title) > DOC_TITLE_MAXLEN:
        flash(f"Title too long (max {DOC_TITLE_MAXLEN}).", "danger")
        return _render_form(400)

    if status not in DOC_STATUSES:
        flash("Invalid status.", "danger")
        return _render_form(400)

    existing_max = (
        db.session.query(sa.func.max(Document.version))
        .filter(Document.buyer_id == buyer_id, Document.doc_type == doc_type)
        .scalar()
    )
    if existing_max is not None and version <= int(existing_max):
        version = int(existing_max) + 1
        flash(f"Version already exists for this buyer + type. Auto-set to v{version}.", "info")

    payload = make_payload_scaffold(doc_type)

    doc = Document(
        buyer_id=buyer_id,
        doc_type=doc_type,
        title=title,
        status=status,
        version=version,
        payload=payload,
        created_by_user_id=getattr(current_user, "id", None),
    )

    db.session.add(doc)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("That buyer + document type + version already exists. Try a higher version.", "danger")
        return _render_form(409)
    except Exception as exc:
        db.session.rollback()
        flash(f"Create document failed: {exc}", "danger")
        return _render_form(500)

    flash("Document created.", "success")
    next_endpoint = next_admin_url_for(doc_type)
    return redirect(url_for(next_endpoint, document_id=str(doc.id)))

@admin_bp.route("/documents/<uuid:document_id>/send-for-signing", methods=["POST"])
@admin_required
def send_document_for_signing(document_id):
    document = Document.query.get_or_404(document_id)

    if document.status in ("buyer_signed", "executed", "void"):
        flash("This document cannot be sent for signing.", "warning")
        return redirect(url_for("admin.documents_view", document_id=str(document.id)))

    token, expires_at = generate_buyer_sign_token(days_valid=7)

    document.buyer_sign_token = token
    document.buyer_sign_token_expires_at = expires_at

    if not _commit_or_rollback("Generate signing link"):
        return redirect(url_for("admin.documents_view", document_id=str(document.id)))

    flash("Signing link generated successfully.", "success")
    return redirect(url_for("admin.documents_view", document_id=str(document.id)))


@admin_bp.route("/documents/<uuid:document_id>", methods=["GET"])
@admin_required
def documents_view(document_id):
    doc = Document.query.get_or_404(document_id)
    # Choose an ordering column safely.
    # If the runtime model has signed_at, use it; otherwise fall back to id.
    sig_order_col = getattr(DocumentSignature, "signed_at", None) or getattr(DocumentSignature, "id")

    signatures = (
        DocumentSignature.query
        .filter(DocumentSignature.document_id == doc.id)
        .order_by(DocumentSignature.signed_at.asc())
        .all()
    )    
    # ----------------------------
    # Audit timeline (events)
    # ----------------------------
    events = []

    if doc.created_at:
        events.append({
            "at": doc.created_at,
            "label": "Created",
            "meta": f"Type: {doc.doc_type} · v{doc.version}",
        })

    if doc.buyer_sign_token_expires_at:
        # Token is generated for 7 days in generate_buyer_sign_token()
        issued_at = doc.buyer_sign_token_expires_at - timedelta(days=7)
        events.append({
            "at": issued_at,
            "label": "Signing link issued",
            "meta": f"Expires: {doc.buyer_sign_token_expires_at}",
        })

    if doc.buyer_signed_at:
        who = " ".join([doc.buyer_sign_name or "", doc.buyer_sign_email or ""]).strip() or "Buyer"
        events.append({
            "at": doc.buyer_signed_at,
            "label": "Buyer signed",
            "meta": who,
        })

    for s in signatures:
        if s.signed_at:
            events.append({
                "at": s.signed_at,
                "label": f"Signature recorded ({s.signer_type})",
                "meta": f"{s.signer_name or '—'} · {s.sign_method or '—'}",
            })

    events = sorted([e for e in events if e.get("at")], key=lambda x: x["at"])

    return render_template(
        "admin/documents_view.html",
        document=doc,
        signatures=signatures,
        doc_statuses=sorted(DOC_STATUSES),
        events=events,
    )
    # ----------------------------
    # Audit timeline (events)
    # ----------------------------
    events = []

    if doc.created_at:
        events.append({
            "at": doc.created_at,
            "label": "Created",
            "meta": f"Type: {doc.doc_type} · v{doc.version}",
        })

    if doc.buyer_sign_token_expires_at:
        issued_at = doc.buyer_sign_token_expires_at - timedelta(days=7)
        events.append({
            "at": issued_at,
            "label": "Signing link issued",
            "meta": f"Expires: {doc.buyer_sign_token_expires_at}",
        })
    if doc.buyer_signed_at:
        who = " ".join([doc.buyer_sign_name or "", doc.buyer_sign_email or ""]).strip() or "Buyer"
        events.append({
            "at": doc.buyer_signed_at,
            "label": "Buyer signed",
            "meta": who,
        })

    for s in signatures:
        if s.signed_at:
            events.append({
                "at": s.signed_at,
                "label": f"Signature recorded ({s.signer_type})",
                "meta": f"{s.signer_name or '—'} · {s.sign_method or '—'}",
            })

    events = sorted([e for e in events if e.get("at")], key=lambda x: x["at"])

    return render_template(
        "admin/documents_view.html",
        document=doc,
        signatures=signatures,
        doc_statuses=sorted(DOC_STATUSES),
        events=events,
    )

@admin_bp.route("/documents/<uuid:document_id>/status", methods=["POST"])
@admin_required
def documents_set_status(document_id):
    doc = Document.query.get_or_404(document_id)
    target = _clean_str(request.form.get("status"))

    if target not in DOC_STATUSES:
        flash("Invalid status.", "danger")
        return redirect(url_for("admin.documents_view", document_id=str(doc.id)))

    if doc.status == "void":
        flash("Void documents cannot be changed.", "danger")
        return redirect(url_for("admin.documents_view", document_id=str(doc.id)))

    doc.status = target
    db.session.add(doc)

    if not _commit_or_rollback("Update document status"):
        return redirect(url_for("admin.documents_view", document_id=str(doc.id)))

    flash(f"Status updated to {target}.", "success")
    return redirect(url_for("admin.documents_view", document_id=str(doc.id)))


@admin_bp.route("/documents/<uuid:document_id>/loi", methods=["GET"])
@admin_required
def documents_loi_preview(document_id):
    doc = Document.query.get_or_404(document_id)
    now_eat = datetime.now(ZoneInfo("Africa/Nairobi"))
    return render_template("pdfs/loi.html", document=doc, now_eat=now_eat)


@admin_bp.route("/documents/<uuid:document_id>/loi.pdf", methods=["GET"])
@admin_required
def documents_loi_pdf(document_id):
    doc = Document.query.get_or_404(document_id)
    now_eat = datetime.now(ZoneInfo("Africa/Nairobi"))

    html = render_template("pdfs/loi.html", document=doc, now_eat=now_eat)
    pdf_bytes = HTML(string=html, base_url=request.host_url).write_pdf()

    buyer_name = doc.buyer.name if doc.buyer else "Buyer"
    filename = f"Rizara_LOI_{_safe_filename(buyer_name)}_v{doc.version}.pdf"

    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@admin_bp.route("/documents/<uuid:document_id>/contract", methods=["GET", "POST"])
@admin_required
def documents_contract_edit(document_id):
    doc = Document.query.get_or_404(document_id)

    if doc.doc_type != "export_sales_contract":
        flash("This editor is only available for export_sales_contract documents.", "warning")
        return redirect(url_for("admin.documents_view", document_id=str(doc.id)))

    if doc.status in ("buyer_signed", "executed", "void"):
        flash("This document can no longer be edited.", "danger")
        return redirect(url_for("admin.documents_view", document_id=str(doc.id)))

    # IMPORTANT:
    # Do NOT do payload = dict(doc.payload) here.
    # We want SQLAlchemy to track changes (MutableDict), and we also force-change detection via flag_modified.
    if doc.payload is None:
        doc.payload = {}

    payload = doc.payload  # MutableDict-backed object

    if request.method == "GET":
        return render_template("admin/document_contract_edit.html", document=doc, payload=payload)

    # --- POST ---
    # ----------------------------
    # Parse + validate fields
    # ----------------------------
    def _to_float(s: str | None):
        try:
            return float(str(s or "").strip())
        except Exception:
            return None

    def _to_int(s: str | None):
        try:
            return int(str(s or "").strip())
        except Exception:
            return None

    incoterm = _clean_str(request.form.get("incoterm"))

    # NEW: product selection + currency
    product_species = _clean_str(request.form.get("product_species")).lower()
    currency = (_clean_str(request.form.get("currency")).upper() or "USD")

    quantity_kg = _to_int(request.form.get("quantity_kg"))
    price_per_kg = _to_float(request.form.get("price_per_kg"))

    advance_percent = _to_int(request.form.get("advance_percent"))
    balance_percent = _to_int(request.form.get("balance_percent"))
    balance_condition = _clean_str(request.form.get("balance_condition"))

    if not incoterm:
        flash("Incoterm is required.", "danger")
        return render_template("admin/document_contract_edit.html", document=doc, payload=payload)

    # NEW: require Goat/Lamb/Beef selection
    if product_species not in ("goat", "lamb", "beef"):
        flash("Product selection is required (Goat / Lamb / Beef).", "danger")
        return render_template("admin/document_contract_edit.html", document=doc, payload=payload)

    if quantity_kg is None or quantity_kg <= 0:
        flash("Quantity (kg) must be a positive whole number.", "danger")
        return render_template("admin/document_contract_edit.html", document=doc, payload=payload)

    if price_per_kg is None or price_per_kg <= 0:
        flash("Price per kg must be a positive number.", "danger")
        return render_template("admin/document_contract_edit.html", document=doc, payload=payload)

    if advance_percent is None or balance_percent is None:
        flash("Advance % and Balance % are required.", "danger")
        return render_template("admin/document_contract_edit.html", document=doc, payload=payload)

    if advance_percent < 0 or advance_percent > 100 or balance_percent < 0 or balance_percent > 100:
        flash("Percentages must be between 0 and 100.", "danger")
        return render_template("admin/document_contract_edit.html", document=doc, payload=payload)

    if advance_percent + balance_percent != 100:
        flash("Advance % + Balance % must equal 100.", "danger")
        return render_template("admin/document_contract_edit.html", document=doc, payload=payload)

    if not balance_condition:
        flash("Balance condition is required (e.g. Against Air Waybill copy).", "danger")
        return render_template("admin/document_contract_edit.html", document=doc, payload=payload)

    # NEW: compute total server-side (do not rely on readonly input posting)
    total_value = round(float(quantity_kg) * float(price_per_kg), 2)

    # ----------------------------
    # Update payload safely
    # NOTE: nested dict edits are not always tracked; we force it with flag_modified().
    # ----------------------------
    payload.setdefault("contract", {})
    payload.setdefault("product", {})
    payload.setdefault("pricing", {})
    payload.setdefault("payment", {})
    payload.setdefault("shipment", {})  # safe, even if you don't use it yet

    payload["contract"]["incoterm"] = incoterm

    # NEW: persist product selection used by PDF
    payload["product"]["species"] = product_species
    payload["product"]["quantity_kg"] = quantity_kg

    payload["pricing"]["price_per_kg"] = round(float(price_per_kg), 4)
    payload["pricing"]["currency"] = currency
    payload["pricing"]["total_value"] = total_value

    payload["payment"]["advance_percent"] = int(advance_percent)
    payload["payment"]["balance_percent"] = int(balance_percent)
    payload["payment"]["balance_condition"] = balance_condition

    # optional toggles (checkboxes)
    payload["payment"]["no_cod"] = bool(request.form.get("no_cod"))
    payload["payment"]["no_payment_after_arrival"] = bool(request.form.get("no_payment_after_arrival"))

    # FORCE SQLAlchemy to persist JSON changes even if nested mutation isn't detected
    flag_modified(doc, "payload")

    db.session.add(doc)
    if not _commit_or_rollback("Update contract payload"):
        return render_template("admin/document_contract_edit.html", document=doc, payload=payload)

    flash("Contract terms updated.", "success")
    return redirect(url_for("admin.documents_view", document_id=str(doc.id)))

@admin_bp.route("/documents/<uuid:document_id>/export-sales-contract", methods=["GET"])
@admin_required
def documents_export_sales_contract_preview(document_id):
    doc = Document.query.get_or_404(document_id)
    if doc.doc_type != "export_sales_contract":
        flash("This preview is only for export_sales_contract documents.", "warning")
        return redirect(url_for("admin.documents_view", document_id=str(doc.id)))

    now_eat = datetime.now(ZoneInfo("Africa/Nairobi"))
    return render_template("pdfs/export_sales_contract.html", document=doc, now_eat=now_eat)


@admin_bp.route("/documents/<uuid:document_id>/export-sales-contract.pdf", methods=["GET"])
@admin_required
def documents_export_sales_contract_pdf(document_id):
    doc = Document.query.get_or_404(document_id)
    if doc.doc_type != "export_sales_contract":
        flash("This PDF is only for export_sales_contract documents.", "warning")
        return redirect(url_for("admin.documents_view", document_id=str(doc.id)))

    now_eat = datetime.now(ZoneInfo("Africa/Nairobi"))
    html = render_template("pdfs/export_sales_contract.html", document=doc, now_eat=now_eat)
    pdf_bytes = HTML(string=html, base_url=request.host_url).write_pdf()

    buyer_name = doc.buyer.name if doc.buyer else "Buyer"
    filename = f"Rizara_Export_Sales_Contract_{_safe_filename(buyer_name)}_v{doc.version}.pdf"

    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp   

@admin_bp.route("/documents/<uuid:document_id>/execute", methods=["POST"])
@admin_required
def documents_execute(document_id):
    doc = Document.query.get_or_404(document_id)

    if doc.status != "buyer_signed":
        flash("Document must be buyer_signed before execution.", "danger")
        return redirect(url_for("admin.documents_view", document_id=str(doc.id)))

    signer_name = getattr(current_user, "name", None) or "Rizara"
    signer_email = getattr(current_user, "email", None)

    sig = DocumentSignature(
        document_id=doc.id,
        signer_type="rizara_admin" if getattr(current_user, "is_admin", False) else "rizara_staff",
        sign_method="typed",
        signer_name=signer_name,
        signer_email=signer_email,
        typed_consent_text="Executed electronically by Rizara.",
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
        signed_by_user_id=getattr(current_user, "id", None),
    )
    db.session.add(sig)

    doc.status = "executed"
    db.session.add(doc)

    if not _commit_or_rollback("Execute document"):
        return redirect(url_for("admin.documents_view", document_id=str(doc.id)))

    flash("Document executed (Rizara internal signature recorded).", "success")
    return redirect(url_for("admin.documents_view", document_id=str(doc.id)))

@admin_bp.route("/documents/<uuid:document_id>/contract.pdf", methods=["GET"])
@admin_required
def documents_contract_pdf(document_id):
    doc = Document.query.get_or_404(document_id)

    if doc.doc_type != "export_sales_contract":
        flash("No contract PDF for this document type.", "warning")
        return redirect(url_for("admin.documents_view", document_id=str(doc.id)))

    if doc.status not in ("buyer_signed", "executed"):
        flash("Contract PDF is available after buyer signs.", "warning")
        return redirect(url_for("admin.documents_view", document_id=str(doc.id)))

    # Prefer immutable snapshot
    if doc.storage_key:
        pdf_bytes = load_document_snapshot_bytes(doc.storage_key)
    else:
        # fallback (should be rare)
        pdf_bytes = render_export_sales_contract_pdf_bytes(doc)

    filename = f"Rizara_Contract_{_safe_filename(doc.buyer.name if doc.buyer else 'Buyer')}_v{doc.version}.pdf"

    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp

@admin_bp.route("/documents/<uuid:document_id>/signed.pdf", methods=["GET"])
@admin_required
def documents_signed_pdf(document_id):
    doc = Document.query.get_or_404(document_id)

    if doc.doc_type != "export_sales_contract":
        flash("Signed PDF is only supported for export sales contracts.", "warning")
        return redirect(url_for("admin.documents_view", document_id=str(doc.id)))

    if doc.status not in ("buyer_signed", "executed"):
        flash("This contract is not signed yet.", "warning")
        return redirect(url_for("admin.documents_view", document_id=str(doc.id)))

    # If snapshot exists, serve it; otherwise generate + store it (useful for older signed docs)
    if doc.storage_key:
        pdf_bytes = load_document_snapshot_bytes(doc.storage_key)
    else:
        pdf_bytes = render_export_sales_contract_pdf_bytes(doc)
        store_document_pdf_snapshot(doc, pdf_bytes=pdf_bytes)
        db.session.commit()

    filename = f"Rizara_Contract_{doc.id}_v{doc.version}_signed.pdf"
    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp