from __future__ import annotations

from backend.extensions import db
from backend.models import User

DEMO_PASSWORD = "Demo2026!"
DEMO_CUSTOMER_INN = "7800000001"
ADMIN_EMAIL = "admin@local.test"
ADMIN_PASSWORD = "Admin2026!"


def ensure_admin_user() -> int:
    """Создаёт локального администратора, если его ещё нет.

    Профиль и пароль задаются только при создании. Если администратор уже
    изменил ФИО, e-mail, организацию или пароль в разделе «Настройки», запуск
    seed/скриптов их не перетирает. Принудительно поддерживаются только роль
    и активность аккаунта, чтобы нельзя было остаться без администратора.
    """
    user = User.query.filter_by(email=ADMIN_EMAIL).first()
    created = 0
    if not user:
        user = User(email=ADMIN_EMAIL)
        user.full_name = "Администратор"
        user.organization_inn = "7800000099"
        user.organization_name = "Администрирование системы"
        user.set_password(ADMIN_PASSWORD)
        db.session.add(user)
        created = 1
    user.account_role = "admin"
    user.is_active = True
    db.session.commit()
    return created


def ensure_demo_users() -> int:
    """Создаёт демо-заказчика и администратора, если их ещё нет.

    No demo USER request is created intentionally: after login the customer
    sees the same empty "Мои заявки" state as a newly registered real user and
    can create the first request themselves. Данные существующих аккаунтов не
    перезаписываются (см. ensure_admin_user).
    """
    created = 0
    user = User.query.filter_by(email="customer@demo.local").first()
    if not user:
        user = User(email="customer@demo.local")
        user.full_name = "Демо Заказчик"
        user.organization_inn = DEMO_CUSTOMER_INN
        user.organization_name = "Демонстрационный заказчик"
        user.set_password(DEMO_PASSWORD)
        db.session.add(user)
        created += 1
    user.account_role = "customer"
    user.is_active = True
    db.session.commit()
    created += ensure_admin_user()
    return created
