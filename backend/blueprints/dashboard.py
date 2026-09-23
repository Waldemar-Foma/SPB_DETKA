from flask import Blueprint, render_template

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@bp.get("/")
def page():
    """Главная аналитическая страница."""
    return render_template(
        "pages/dashboard.html",
        page_id="dashboard",
        page_title="Дашборд",
    )
