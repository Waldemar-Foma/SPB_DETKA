"""Страница «Контракты»."""
from flask import Blueprint, render_template

bp = Blueprint("contracts", __name__, url_prefix="/contracts")


@bp.get("/")
def page():
    return render_template(
        "pages/contracts.html",
        page_id="contracts",
        page_title="Контракты",
    )
