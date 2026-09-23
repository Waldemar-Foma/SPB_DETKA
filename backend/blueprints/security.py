"""Страница «Проверка СБ»."""
from flask import Blueprint, render_template

bp = Blueprint("security", __name__, url_prefix="/security")


@bp.get("/")
def page():
    return render_template(
        "pages/security.html",
        page_id="security",
        page_title="Проверка СБ",
    )
