from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

from flask import Blueprint, redirect, render_template, request, url_for

from backend.extensions import db
from backend.models import User
from backend.services.auth import current_user, login_user, logout_user

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _clean_inn(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _safe_next(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.netloc or parsed.scheme:
        return None
    return value if value.startswith("/") else None


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect(url_for("admin.page" if current_user().account_role == "admin" else "contracts.page"))

    errors: list[str] = []
    values = {
        "full_name": request.form.get("full_name", "").strip(),
        "email": request.form.get("email", "").strip().lower(),
        "organization_inn": _clean_inn(request.form.get("organization_inn", "")),
        "organization_name": request.form.get("organization_name", "").strip(),
    }

    if request.method == "POST":
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        if len(values["full_name"]) < 2:
            errors.append("Укажите имя пользователя.")
        if "@" not in values["email"] or len(values["email"]) < 5:
            errors.append("Укажите корректный e-mail.")
        if User.query.filter_by(email=values["email"]).first():
            errors.append("Пользователь с таким e-mail уже зарегистрирован.")
        if len(values["organization_inn"]) not in (10, 12):
            errors.append("ИНН организации должен содержать 10 или 12 цифр.")
        if len(password) < 8:
            errors.append("Пароль должен содержать минимум 8 символов.")
        if password != password2:
            errors.append("Пароли не совпадают.")

        if not errors:
            user = User(
                email=values["email"],
                full_name=values["full_name"],
                account_role="customer",
                organization_inn=values["organization_inn"],
                organization_name=values["organization_name"],
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for("contracts.page"))

    return render_template("auth/register.html", page_title="Регистрация", values=values, errors=errors)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("admin.page" if current_user().account_role == "admin" else "contracts.page"))

    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if not user or not user.is_active or not user.check_password(password):
            error = "Неверный e-mail или пароль."
        else:
            user.last_login_at = datetime.utcnow()
            db.session.commit()
            login_user(user)
            default_endpoint = "admin.page" if user.account_role == "admin" else "contracts.page"
            return redirect(_safe_next(request.args.get("next")) or url_for(default_endpoint))

    return render_template("auth/login.html", page_title="Вход", error=error)


@bp.route("/logout", methods=["GET", "POST"])
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
