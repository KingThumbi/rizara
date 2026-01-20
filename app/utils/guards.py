from functools import wraps
from flask import abort
from flask_login import login_required, current_user

def admin_required(view):
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
