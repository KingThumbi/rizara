# app/admin.py
from __future__ import annotations

import sqlalchemy as sa
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import desc
from werkzeug.security import generate_password_hash

from .extensions import db
from .models import Buyer, Document, DocumentSignature, User
from .constants.roles import ROLES
from .utils.auth import allowed_roles_for
from .utils.guards import admin_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
DOC_STATUSES = {"draft", "buyer_signed", "executed", "expired", "void"}
DOC_TYPE_MAXLEN = 50
DOC_TITLE_MAXLEN = 200


def _commit_or_rollback(action: str) -> bool:
    """Commit session; rollback + flash on failure. Returns True on success."""
    try:
        db.session.commit()
        return True
    except Exception as exc:
        db.session.rollback()
        flash(f"{action} failed: {exc}", "danger")
        return False


def _clean_str(value: str | None) -> str:
    return (value or "").strip()


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

    if request.method == "GET":
        return render_template(
            "admin/documents_new.html",
            buyers=buyers,
            doc_statuses=sorted(DOC_STATUSES),
        )

    buyer_id = request.form.get("buyer_id", type=int)
    doc_type = _clean_str(request.form.get("doc_type")).lower()
    title = _clean_str(request.form.get("title"))
    version = request.form.get("version", type=int) or 1
    status = _clean_str(request.form.get("status") or "draft") or "draft"

    if not buyer_id:
        flash("Select a buyer.", "danger")
        return render_template("admin/documents_new.html", buyers=buyers, doc_statuses=sorted(DOC_STATUSES))

    buyer = Buyer.query.get(buyer_id)
    if not buyer:
        flash("Buyer not found.", "danger")
        return render_template("admin/documents_new.html", buyers=buyers, doc_statuses=sorted(DOC_STATUSES))

    if not doc_type:
        flash("Document type is required (e.g. loi).", "danger")
        return render_template("admin/documents_new.html", buyers=buyers, doc_statuses=sorted(DOC_STATUSES))

    if len(doc_type) > DOC_TYPE_MAXLEN:
        flash(f"Document type too long (max {DOC_TYPE_MAXLEN}).", "danger")
        return render_template("admin/documents_new.html", buyers=buyers, doc_statuses=sorted(DOC_STATUSES))

    if not title:
        flash("Title is required.", "danger")
        return render_template("admin/documents_new.html", buyers=buyers, doc_statuses=sorted(DOC_STATUSES))

    if len(title) > DOC_TITLE_MAXLEN:
        flash(f"Title too long (max {DOC_TITLE_MAXLEN}).", "danger")
        return render_template("admin/documents_new.html", buyers=buyers, doc_statuses=sorted(DOC_STATUSES))

    if status not in DOC_STATUSES:
        flash("Invalid status.", "danger")
        return render_template("admin/documents_new.html", buyers=buyers, doc_statuses=sorted(DOC_STATUSES))

    doc = Document(
        buyer_id=buyer_id,
        doc_type=doc_type,
        title=title,
        status=status,
        version=version,
        created_by_user_id=getattr(current_user, "id", None),
    )

    db.session.add(doc)
    if not _commit_or_rollback("Create document"):
        return render_template("admin/documents_new.html", buyers=buyers, doc_statuses=sorted(DOC_STATUSES))

    flash("Document created.", "success")
    return redirect(url_for("admin.documents_view", document_id=str(doc.id)))


@admin_bp.route("/documents/<uuid:document_id>", methods=["GET"])
@admin_required
def documents_view(document_id):
    doc = Document.query.get_or_404(document_id)

    signatures = (
        DocumentSignature.query.filter_by(document_id=doc.id)
        .order_by(DocumentSignature.signed_at.asc())
        .all()
    )

    return render_template(
        "admin/documents_view.html",
        document=doc,          # ✅ ORM object
        signatures=signatures,
        doc_statuses=sorted(DOC_STATUSES)
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
