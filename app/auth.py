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
from .utils.guards import admin_required, requires_terms

auth = Blueprint("auth", __name__)

# =========================================================
# Terms & Conditions (versioned)
# =========================================================
TERMS_VERSION = "v1.0"


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
    """
    Allow only same-host redirects AND block redirect loops into /login or /logout.
    """
    if not target:
        return False

    blocked_prefixes = ("/login", "/logout")
    if target.startswith(blocked_prefixes):
        return False

    ref = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return test.scheme in ("http", "https") and ref.netloc == test.netloc


def _next_or_dashboard() -> str:
    nxt = request.args.get("next") or request.form.get("next") or ""
    if nxt and _is_safe_next(nxt):
        return nxt
    return url_for("main.dashboard")


def _normalize_role(role: str) -> str:
    """
    Normalize role strings to prevent mismatches like 'super-admin' vs 'super_admin'.
    """
    return (role or "").strip().lower().replace("-", "_")


# =========================================================
# Change Password (Logged-in users)
# =========================================================
@auth.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = (request.form.get("current_password") or "").strip()
        new_password = (request.form.get("new_password") or "").strip()
        confirm_password = (request.form.get("confirm_password") or "").strip()

        if not current_password or not new_password or not confirm_password:
            flash("All fields are required.", "danger")
            return render_template("auth/change_password.html", current_year=datetime.utcnow().year)

        if not check_password_hash(current_user.password_hash, current_password):
            flash("Current password is incorrect.", "danger")
            return render_template("auth/change_password.html", current_year=datetime.utcnow().year)

        if len(new_password) < 10:
            flash("New password must be at least 10 characters.", "danger")
            return render_template("auth/change_password.html", current_year=datetime.utcnow().year)

        if new_password != confirm_password:
            flash("New password and confirmation do not match.", "danger")
            return render_template("auth/change_password.html", current_year=datetime.utcnow().year)

        if check_password_hash(current_user.password_hash, new_password):
            flash("New password must be different from the current password.", "danger")
            return render_template("auth/change_password.html", current_year=datetime.utcnow().year)

        current_user.password_hash = generate_password_hash(new_password)

        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            flash("Failed to update password. Please try again.", "danger")
            return render_template("auth/change_password.html", current_year=datetime.utcnow().year)

        flash("Password updated successfully.", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("auth/change_password.html", current_year=datetime.utcnow().year)


# =========================================================
# Login / Logout
# =========================================================
@auth.route("/login", methods=["GET", "POST"])
def login():
    if getattr(current_user, "is_authenticated", False):
        return redirect(url_for("main.dashboard"))

    next_url = request.args.get("next") or request.form.get("next") or ""

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("Email and password are required.", "danger")
            return render_template("login.html", next=next_url, current_year=datetime.utcnow().year)

        user = User.query.filter(db.func.lower(User.email) == email).first()

        # If your model has is_active, enforce it
        if user and hasattr(user, "is_active") and user.is_active is False:
            flash("This account is inactive. Contact an admin.", "danger")
            return render_template("login.html", next=next_url, current_year=datetime.utcnow().year)

        if not user or not check_password_hash(user.password_hash, password):
            flash("Invalid email or password.", "danger")
            return render_template("login.html", next=next_url, current_year=datetime.utcnow().year)

        login_user(user)

        # Stamp last_login_at if exists
        if hasattr(user, "last_login_at"):
            try:
                user.last_login_at = datetime.utcnow()
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()

        return redirect(_next_or_dashboard())

    return render_template("login.html", next=next_url, current_year=datetime.utcnow().year)


@auth.route("/logout")
def logout():
    """
    IMPORTANT: logout must NOT be login_required, otherwise Flask-Login redirects to
    /login?next=/logout and you get a loop after successful login.
    """
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))


# =========================================================
# Terms: Accept (External users only)
# =========================================================
@auth.route("/accept-terms", methods=["GET", "POST"])
@login_required
def accept_terms():
    # Internal roles should never be forced here
    if not requires_terms(current_user):
        return redirect(url_for("main.dashboard"))

    next_url = request.args.get("next") or request.form.get("next") or ""

    if request.method == "POST":
        accepted = request.form.get("accept_terms") == "yes"

        if not accepted:
            flash("You must accept the Terms & Conditions to continue.", "danger")
            return render_template(
                "auth/accept_terms.html",
                next=next_url,
                current_year=datetime.utcnow().year,
                terms_version=TERMS_VERSION,
            )

        current_user.accepted_terms = True
        current_user.accepted_terms_at = datetime.utcnow()

        # Optional future-proof field
        if hasattr(current_user, "terms_version"):
            current_user.terms_version = TERMS_VERSION

        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            flash("Could not save your acceptance. Please try again.", "danger")
            return render_template(
                "auth/accept_terms.html",
                next=next_url,
                current_year=datetime.utcnow().year,
                terms_version=TERMS_VERSION,
            )

        flash("Terms accepted successfully.", "success")

        if next_url and _is_safe_next(next_url):
            return redirect(next_url)

        return redirect(url_for("main.dashboard"))

    return render_template(
        "auth/accept_terms.html",
        next=next_url,
        current_year=datetime.utcnow().year,
        terms_version=TERMS_VERSION,
    )


# =========================================================
# Admin: List / Search / Filter Users
# =========================================================
@auth.route("/admin/users", methods=["GET"])
@admin_required
def admin_list_users():
    q = (request.args.get("q") or "").strip()
    role = _normalize_role(request.args.get("role") or "")
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
    Template expected: templates/admin/users_new.html
    """
    return render_template("admin/users_new.html", current_year=datetime.utcnow().year)


# =========================================================
# Admin: Create User (POST submit)
# =========================================================
@auth.route("/admin/users/new", methods=["POST"])
@admin_required
def admin_create_user_submit():
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    phone = (request.form.get("phone") or "").strip() or None
    role = _normalize_role(request.form.get("role") or "")
    password = request.form.get("password") or ""

    if not name or not email or not role or not password:
        flash("Name, email, role, and password are required.", "danger")
        return redirect(url_for("auth.admin_create_user"))

    # Normalize admin flags
    is_admin_role = role in ("admin", "super_admin")

    user = User(
        name=name,
        email=email,
        phone=phone,
        role=role,
        is_admin=is_admin_role if hasattr(User, "is_admin") else None,
        password_hash=generate_password_hash(password),
    )

    # If your model has is_active, default it safely
    if hasattr(User, "is_active") and getattr(user, "is_active", None) is None:
        user.is_active = True

    # If your model has terms fields, admins/staff can be pre-marked as accepted
    if hasattr(User, "accepted_terms") and not requires_terms(user):
        user.accepted_terms = True
        if hasattr(User, "accepted_terms_at"):
            user.accepted_terms_at = datetime.utcnow()
        if hasattr(User, "terms_version"):
            user.terms_version = TERMS_VERSION

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
