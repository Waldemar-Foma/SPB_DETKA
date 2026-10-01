from flask import Blueprint, redirect, url_for
from backend.services.auth import current_user

bp = Blueprint("main", __name__)

@bp.get("/")
def index():
    user = current_user()
    if not user or not user.is_active:
        return redirect(url_for("auth.login"))
    return redirect(url_for("admin.page" if user.account_role == "admin" else "contracts.page"))
