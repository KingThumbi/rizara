# app/utils/auth.py
"""
Authentication helpers and routes for Rizara.

- Secure password hashing & verification
- Strong password policy enforcement
- Rate-limited login
- Admin-only user creation
- Admin list users page (search/filter/paginate)
- No /auth namespace required
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse, urljoin

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import (
    login_user,
    logout_user,
    current_user,
    login_required,
)
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app.extensions import db, limiter
from app.models import User
from app.constants.permissions import ROLE_CREATION_RULES

from .guards import admin_required
from .passwords import hash_password, verify_password, validate_password

auth = Blueprint("auth", __name__)  # registered at "/" (not /auth)


# =========================================================
# Helpers
# =========================================================
def allowed_roles_for(user: User) -> list[str]:
    return ROLE_CREATION_RULES.get((user.role or "").lower(), [])


def _is_safe_next(target: str) -> bool:
    if not target:
        return False
    ref = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return test.scheme in ("http", "https") and ref.netloc == test.netloc


def _next_or_dashboard():
    nxt = request.args.get("next") or request.form.get("next")
    if nxt and _is_safe_next(nxt):
        return nxt
    return url_for("main.dashboard")


# =========================================================
# Login / Logout
# =========================================================
@auth.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("Email and password are required.", "danger")
            return redirect(request.url)

        user = User.query.filter(db.func.lower(User.email) == email).first()
        if not user or not verify_password(user.password_hash, password):
            flash("Invalid email or password.", "danger")
            return redirect(request.url)

        remember = bool(request.form.get("remember"))
        login_user(user, remember=remember)
        return redirect(_next_or_dashboard())

    # Uses templates/login.html
    return render_template("login.html", next=request.args.get("next"))


@auth.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# =========================================================
# Admin: Create User
# =========================================================
@auth.route("/admin/users/new", methods=["GET", "POST"])
@admin_required
def admin_create_user():
    roles = allowed_roles_for(current_user)

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        phone = (request.form.get("phone") or "").strip() or None
        role = (request.form.get("role") or "").strip().lower()
        password = request.form.get("password") or ""

        if not name or not email or not role or not password:
            flash("All fields are required.", "danger")
            return redirect(request.url)

        if roles and role not in roles:
            flash("You are not allowed to create that role.", "danger")
            return redirect(request.url)

        ok, msg = validate_password(password)
        if not ok:
            flash(msg, "danger")
            return redirect(request.url)

        user = User(
            name=name,
            email=email,
            phone=phone,
            role=role,
            is_admin=role in ("admin", "super-admin"),
            password_hash=hash_password(password),
        )

        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Email or phone already exists.", "danger")
            return redirect(request.url)

        flash("User created successfully.", "success")
        return redirect(url_for("main.dashboard"))

    # Uses templates/users_new.html
    return render_template("users_new.html", roles=roles)


# =========================================================
# Admin: List Users (search/filter/paginate)
# =========================================================
@auth.route("/admin/users", methods=["GET"])
@admin_required
def admin_list_users():
    """
    Admin: list/search/filter users.
    URL examples:
      /admin/users
      /admin/users?q=michael
      /admin/users?role=admin
      /admin/users?status=active
      /admin/users?page=2
    """
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

    # Works after you add is_active to User model (recommended).
    if status in ("active", "inactive") and hasattr(User, "is_active"):
        qry = qry.filter(User.is_active.is_(status == "active"))

    pagination = qry.order_by(User.id.desc()).paginate(page=page, per_page=per_page, error_out=False)

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
# Change Password (any logged-in user)
# =========================================================
@auth.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_pw = request.form.get("current_password") or ""
        new_pw = request.form.get("new_password") or ""
        confirm_pw = request.form.get("confirm_password") or ""

        if not current_pw or not new_pw or not confirm_pw:
            flash("All fields are required.", "danger")
            return redirect(request.url)

        if not verify_password(current_user.password_hash, current_pw):
            flash("Current password is incorrect.", "danger")
            return redirect(request.url)

        if new_pw != confirm_pw:
            flash("Passwords do not match.", "danger")
            return redirect(request.url)

        ok, msg = validate_password(new_pw)
        if not ok:
            flash(msg, "danger")
            return redirect(request.url)

        current_user.password_hash = hash_password(new_pw)
        db.session.commit()

        flash("Password updated successfully.", "success")
        return redirect(url_for("main.dashboard"))

    # Uses templates/change_password.html
    return render_template("change_password.html")
