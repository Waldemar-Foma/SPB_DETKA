"""Страница «Поставщики»: полный реестр."""
from flask import Blueprint, render_template

bp = Blueprint("suppliers_page", __name__, url_prefix="/suppliers")


@bp.get("/")
def page():
    return render_template(
        "pages/suppliers.html",
        page_id="suppliers",
        page_title="Поставщики",
    )
