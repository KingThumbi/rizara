from __future__ import annotations

from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required

pipeline_pages_bp = Blueprint(
    "pipeline_pages",
    __name__,
    url_prefix="/admin/pipeline",
)


@pipeline_pages_bp.get("/")
@login_required
def pipeline_dashboard_slash():
    return redirect(url_for("pipeline_pages.pipeline_dashboard"))


@pipeline_pages_bp.get("")
@login_required
def pipeline_dashboard():
    return render_template("admin/pipeline/dashboard.html")


@pipeline_pages_bp.get("/cases/<int:case_id>/")
@login_required
def pipeline_case_detail_slash(case_id: int):
    return redirect(url_for("pipeline_pages.pipeline_case_detail", case_id=case_id))


@pipeline_pages_bp.get("/cases/<int:case_id>")
@login_required
def pipeline_case_detail(case_id: int):
    return render_template("admin/pipeline/case_detail.html", case_id=case_id)