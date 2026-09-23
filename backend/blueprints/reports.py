"""Страница «Отчёты»."""
from flask import Blueprint, render_template

bp = Blueprint("reports", __name__, url_prefix="/reports")


@bp.get("/")
def page():
    return render_template(
        "pages/reports.html",
        page_id="reports",
        page_title="Отчёты",
    )
