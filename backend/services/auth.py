from __future__ import annotations

from functools import wraps

from flask import jsonify, redirect, request, session, url_for

from backend.models import User


def current_user() -> User | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return User.query.get(user_id)


def login_user(user: User) -> None:
    session.clear()
    session["user_id"] = user.id
    session.permanent = True


def logout_user() -> None:
    session.clear()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user and user.is_active:
            return view(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify({"error": {"code": "auth_required", "message": "Необходимо войти в аккаунт"}}), 401
        return redirect(url_for("auth.login", next=request.full_path))
    return wrapped


def customer_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user or not user.is_active:
            return jsonify({"error": {"code": "auth_required", "message": "Чтобы выбрать исполнителя, войдите как заказчик"}}), 401
        if user.account_role != "customer":
            return jsonify({"error": {"code": "customer_only", "message": "Итогового исполнителя может выбирать только заказчик"}}), 403
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user or not user.is_active:
            if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
                return jsonify({"error": {"code": "auth_required", "message": "Необходимо войти в аккаунт администратора"}}), 401
            return redirect(url_for("auth.login", next=request.full_path))
        if user.account_role != "admin":
            if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
                return jsonify({"error": {"code": "admin_only", "message": "Доступно только администратору"}}), 403
            return redirect(url_for("dashboard.page"))
        return view(*args, **kwargs)
    return wrapped
