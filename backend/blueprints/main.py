from flask import Blueprint, redirect, url_for

bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    """Корень перенаправляет на дашборд."""
    return redirect(url_for("dashboard.page"))
