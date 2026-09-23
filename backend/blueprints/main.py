from flask import Blueprint, render_template

bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    """Главная страница — дашборд поиска."""
    return render_template("search.html")