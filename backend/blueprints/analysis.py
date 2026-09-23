"""Страница «Анализ ТЗ»."""
from flask import Blueprint, render_template

bp = Blueprint("analysis", __name__, url_prefix="/analysis")


@bp.get("/")
def page():
    return render_template(
        "pages/analysis.html",
        page_id="analysis",
        page_title="Анализ ТЗ",
    )
