# app/utils/guards.py

from __future__ import annotations

from functools import wraps
from datetime import datetime
from typing import Callable, Any

from flask import abort, redirect, url_for, request
from flask_login import login_required, current_user


# Roles that should NOT be forced to accept external Terms & Conditions
TERMS_EXEMPT_ROLES = {"admin", "super_admin", "staff"}


def requires_terms(user) -> bool:
    """
    Returns True if the user must accept Terms & Conditions before accessing the platform.
    External users (buyers, farmers, transporters, service providers, etc.) should accept terms.
    Internal roles (admin/staff) are exempt.
    """
    if not user:
        return False

    role = getattr(user, "role", None)
    if not role:
        # If role is missing, treat as external (safer default)
        return True

    return role not in TERMS_EXEMPT_ROLES


def admin_required(view: Callable[..., Any]) -> Callable[..., Any]:
    """
    Allow only admin and super_admin.
    Returns 403 for all other logged-in roles.
    """
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        role = getattr(current_user, "role", None)
        if role not in ("admin", "super_admin"):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def role_required(*allowed_roles: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Generic role gate:
        @role_required("buyer", "farmer")
        def view(): ...
    """
    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            role = getattr(current_user, "role", None)
            if role not in allowed_roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def terms_required(view: Callable[..., Any]) -> Callable[..., Any]:
    """
    Enforces Terms acceptance for external users only.
    Redirects to the accept-terms page if not accepted.
    NOTE: Keep accept-terms endpoint name consistent with your auth blueprint.
    """
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if requires_terms(current_user) and not getattr(current_user, "accepted_terms", False):
            # prevent redirect loops if someone directly hits accept-terms
            if request.endpoint != "auth.accept_terms":
                return redirect(url_for("auth.accept_terms"))
        return view(*args, **kwargs)
    return wrapped
