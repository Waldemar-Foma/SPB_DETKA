from __future__ import annotations

import re

from flask import Blueprint, jsonify, render_template, request

from backend.blueprints.auth import _clean_inn, _password_errors
from backend.extensions import db
from backend.models import Procurement, User
from backend.services.auth import current_user, login_required, login_user

bp = Blueprint("settings", __name__, url_prefix="/settings")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _error(message, status=400, field=None, errors=None):
    payload = {"error": {"code": "validation_error", "message": message}}
    if field:
        payload["error"]["field"] = field
    if errors:
        payload["error"]["errors"] = errors
    return jsonify(payload), status


def _profile_payload(user: User) -> dict:
    return {
        "full_name": user.full_name,
        "email": user.email,
        "organization_inn": user.organization_inn,
        "organization_name": user.organization_name or "",
        "role_label": user.role_label,
        "initials": user.initials,
    }


@bp.get("/")
@login_required
def page():
    return render_template(
        "pages/settings.html",
        page_id="settings",
        page_title="Настройки",
        profile=_profile_payload(current_user()),
    )


@bp.post("/api/profile")
@login_required
def update_profile():
    """ФИО и e-mail."""
    user = current_user()
    data = request.get_json(silent=True) or {}
    full_name = " ".join(str(data.get("full_name", "")).split())
    email = str(data.get("email", "")).strip().lower()

    if len(full_name) < 2:
        return _error("Укажите ФИО (минимум 2 символа).", field="full_name")
    if len(full_name) > 255:
        return _error("ФИО слишком длинное.", field="full_name")
    if not EMAIL_RE.match(email) or len(email) > 255:
        return _error("Укажите корректный e-mail.", field="email")
    taken = User.query.filter(User.email == email, User.id != user.id).first()
    if taken:
        return _error("Этот e-mail уже используется другим пользователем.", field="email")

    user.full_name = full_name
    user.email = email
    db.session.commit()
    # В сессии хранится e-mail, поэтому после его смены сессию нужно обновить,
    # иначе current_user() посчитает cookie устаревшей и разлогинит пользователя.
    login_user(user)
    return jsonify({"ok": True, "message": "Данные профиля сохранены.", "profile": _profile_payload(user)})


@bp.post("/api/organization")
@login_required
def update_organization():
    """ИНН и название организации (например, ООО «Компания»)."""
    user = current_user()
    data = request.get_json(silent=True) or {}
    inn = _clean_inn(str(data.get("organization_inn", "")))
    name = " ".join(str(data.get("organization_name", "")).split())

    if len(inn) not in (10, 12):
        return _error("ИНН организации должен содержать 10 или 12 цифр.", field="organization_inn")
    if len(name) > 255:
        return _error("Название организации слишком длинное.", field="organization_name")

    old_inn = user.organization_inn
    migrated = 0
    if inn != old_inn:
        # Заявки привязаны к ИНН организации. Если в организации больше никого нет,
        # переносим заявки на новый ИНН, иначе они «пропадут» из списка заказчика.
        # Если по старому ИНН работают другие пользователи, заявки остаются у них.
        colleagues = User.query.filter(User.organization_inn == old_inn, User.id != user.id).count()
        if colleagues == 0:
            migrated = Procurement.query.filter_by(customer_inn=old_inn, source_system="USER").update(
                {"customer_inn": inn}, synchronize_session=False
            )
        user.organization_inn = inn
    user.organization_name = name
    db.session.commit()

    message = "Данные организации сохранены."
    if migrated:
        message += f" Заявок перенесено на новый ИНН: {migrated}."
    return jsonify({"ok": True, "message": message, "migrated_requests": migrated, "profile": _profile_payload(user)})


@bp.post("/api/password")
@login_required
def update_password():
    user = current_user()
    data = request.get_json(silent=True) or {}
    current = str(data.get("current_password", ""))
    new = str(data.get("new_password", ""))
    new2 = str(data.get("new_password2", ""))

    if not user.check_password(current):
        return _error("Текущий пароль указан неверно.", field="current_password")
    errors = _password_errors(new)
    if errors:
        return _error(errors[0], field="new_password", errors=errors)
    if new != new2:
        return _error("Новые пароли не совпадают.", field="new_password2")
    if new == current:
        return _error("Новый пароль должен отличаться от текущего.", field="new_password")

    user.set_password(new)
    db.session.commit()
    login_user(user)
    return jsonify({"ok": True, "message": "Пароль изменён."})
