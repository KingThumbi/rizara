# app/auth.py

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse, urljoin

from flask import Blueprint, request, redirect, url_for, render_template, flash
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .models import User
from .extensions import login_manager, db
from .utils.guards import admin_required

auth = Blueprint("auth", __name__)


# =========================================================
# Flask-Login user loader
# =========================================================
@login_manager.user_loader
def load_user(user_id: str):
    try:
        return db.session.get(User, int(user_id))
    except Exception:
        return None


# =========================================================
# Helpers
# =========================================================
def _is_safe_next(target: str) -> bool:
    if not target:
        return False
    ref = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return test.scheme in ("http", "https") and ref.netloc == test.netloc


def _next_or_dashboard() -> str:
    nxt = request.args.get("next") or request.form.get("next")
    if nxt and _is_safe_next(nxt):
        return nxt
    return url_for("main.dashboard")


# =========================================================
# Login / Logout
# =========================================================
@auth.route("/login", methods=["GET", "POST"])
def login():
    if getattr(current_user, "is_authenticated", False):
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("Email and password are required.", "danger")
            return redirect(request.url)

        user = User.query.filter(db.func.lower(User.email) == email).first()

        # If your model has is_active, enforce it
        if user and hasattr(user, "is_active") and user.is_active is False:
            flash("This account is inactive. Contact an admin.", "danger")
            return redirect(request.url)

        if not user or not check_password_hash(user.password_hash, password):
            flash("Invalid email or password.", "danger")
            return redirect(request.url)

        login_user(user)

        # Stamp last_login_at if exists
        if hasattr(user, "last_login_at"):
            try:
                user.last_login_at = datetime.utcnow()
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()

        return redirect(_next_or_dashboard())

    return render_template("login.html", next=request.args.get("next"))


@auth.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))


# =========================================================
# Admin: List / Search / Filter Users
# =========================================================
@auth.route("/admin/users", methods=["GET"])
@admin_required
def admin_list_users():
    q = (request.args.get("q") or "").strip()
    role = (request.args.get("role") or "").strip().lower()
    status = (request.args.get("status") or "").strip().lower()
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)

    qry = User.query

    if q:
        like = f"%{q.lower()}%"
        qry = qry.filter(
            or_(
                db.func.lower(User.name).like(like),
                db.func.lower(User.email).like(like),
                db.func.lower(User.phone).like(like),
            )
        )

    if role:
        qry = qry.filter(db.func.lower(User.role) == role)

    if status in ("active", "inactive") and hasattr(User, "is_active"):
        qry = qry.filter(User.is_active.is_(status == "active"))

    pagination = qry.order_by(User.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template(
        "admin/users_list.html",
        users=pagination.items,
        pagination=pagination,
        q=q,
        role=role,
        status=status,
        per_page=per_page,
        current_year=datetime.utcnow().year,
    )


# =========================================================
# Admin: Create User (GET form)
# =========================================================
@auth.route("/admin/users/new", methods=["GET"])
@admin_required
def admin_create_user():
    """
    Renders the create-user form.
    Template expected: templates/users_new.html
    """
    return render_template("users_new.html", current_year=datetime.utcnow().year)


# =========================================================
# Admin: Create User (POST submit)
# =========================================================
@auth.route("/admin/users/new", methods=["POST"])
@admin_required
def admin_create_user_submit():
    """
    Handles form submit for creating users.
    """
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    phone = (request.form.get("phone") or "").strip() or None
    role = (request.form.get("role") or "").strip().lower()
    password = request.form.get("password") or ""

    if not name or not email or not role or not password:
        flash("Name, email, role, and password are required.", "danger")
        return redirect(url_for("auth.admin_create_user"))

    user = User(
        name=name,
        email=email,
        phone=phone,
        role=role,
        is_admin=role in ("admin", "super-admin"),
        password_hash=generate_password_hash(password),
    )

    # If your model has is_active, default it safely
    if hasattr(User, "is_active") and user.is_active is None:
        user.is_active = True

    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Email or phone already exists.", "danger")
        return redirect(url_for("auth.admin_create_user"))
    except SQLAlchemyError:
        db.session.rollback()
        flash("Failed to create user. Try again.", "danger")
        return redirect(url_for("auth.admin_create_user"))

    flash("User created successfully.", "success")
    return redirect(url_for("auth.admin_list_users"))
