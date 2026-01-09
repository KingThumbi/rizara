from flask import Blueprint, request, redirect, url_for, render_template
from flask_login import login_user, logout_user
from werkzeug.security import check_password_hash

from .models import User
from .extensions import login_manager

auth = Blueprint("auth", __name__)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form["email"]).first()
        if user and check_password_hash(
            user.password_hash,
            request.form["password"]
        ):
            login_user(user)
            return redirect(url_for("main.dashboard"))  # safe default

    return render_template("login.html")


@auth.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
