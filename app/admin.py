from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash
from werkzeug.security import generate_password_hash

from .extensions import db
from .models import User
from .constants.roles import ROLES
from .utils.auth import allowed_roles_for
from .utils.guards import admin_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# -----------------------
# API: roles allowed
# GET /admin/roles
# -----------------------
@admin_bp.route("/roles", methods=["GET"])
@admin_required
def get_creatable_roles():
    roles = allowed_roles_for(User.query.get(int(getattr(__import__("flask_login").current_user, "id"))))  # safe fallback
    # But simpler and correct: use current_user directly (kept minimal below)
    from flask_login import current_user
    roles = allowed_roles_for(current_user)

    return jsonify({
        "current_role": getattr(current_user, "role", None),
        "allowed_roles": [{"key": r, "label": ROLES.get(r, r)} for r in roles]
    }), 200


# -----------------------
# API: create user (JSON)
# POST /admin/users
# -----------------------
@admin_bp.route("/users", methods=["POST"])
@admin_required
def create_user_api():
    from flask_login import current_user

    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip() or None
    password = data.get("password")
    role = data.get("role")

    if not name or not email or not password or not role:
        return jsonify({"error": "name, email, password and role are required"}), 400

    if role not in ROLES:
        return jsonify({"error": "Invalid role"}), 400

    allowed = allowed_roles_for(current_user)
    if role not in allowed:
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
    db.session.commit()

    return jsonify({
        "message": "User created successfully",
        "user": {"id": user.id, "email": user.email, "role": user.role}
    }), 201


# -----------------------
# Jinja page: create user form
# GET /admin/users/new
# -----------------------
@admin_bp.route("/users/new", methods=["GET"])
@admin_required
def create_user_page():
    from flask_login import current_user

    allowed = allowed_roles_for(current_user)
    role_options = [{"key": r, "label": ROLES.get(r, r)} for r in allowed]
    return render_template("admin/users_new.html", role_options=role_options)


# -----------------------
# Jinja submit handler
# POST /admin/users/new
# -----------------------
@admin_bp.route("/users/new", methods=["POST"])
@admin_required
def create_user_submit():
    from flask_login import current_user

    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    phone = (request.form.get("phone") or "").strip() or None
    password = request.form.get("password")
    role = request.form.get("role")

    if not name or not email or not password or not role:
        flash("Name, email, password, and role are required.", "danger")
        return redirect(url_for("admin.create_user_page"))

    if role not in ROLES:
        flash("Invalid role selected.", "danger")
        return redirect(url_for("admin.create_user_page"))

    allowed = allowed_roles_for(current_user)
    if role not in allowed:
        flash("Not allowed to create that role.", "danger")
        return redirect(url_for("admin.create_user_page"))

    if User.query.filter_by(email=email).first():
        flash("Email already exists.", "danger")
        return redirect(url_for("admin.create_user_page"))

    if phone and User.query.filter_by(phone=phone).first():
        flash("Phone already exists.", "danger")
        return redirect(url_for("admin.create_user_page"))

    user = User(
        name=name,
        email=email,
        phone=phone,
        role=role,
        is_admin=role in ("admin", "super_admin"),
        password_hash=generate_password_hash(password),
    )

    db.session.add(user)
    db.session.commit()

    flash(f"User created: {user.email} ({user.role})", "success")
    return redirect(url_for("admin.create_user_page"))
