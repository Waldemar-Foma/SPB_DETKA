from __future__ import annotations

from backend.extensions import db
from backend.models import User

DEMO_PASSWORD = "demo2026"
DEMO_CUSTOMER_INN = "7800000001"
ADMIN_EMAIL = "admin@local.test"
ADMIN_PASSWORD = "admin2026"


def ensure_admin_user() -> int:
    """Create/update the local service administrator."""
    user = User.query.filter_by(email=ADMIN_EMAIL).first()
    created = 0
    if not user:
        user = User(email=ADMIN_EMAIL)
        db.session.add(user)
        created = 1
    user.full_name = "Администратор"
    user.account_role = "admin"
    user.organization_inn = "7800000099"
    user.organization_name = "Администрирование системы"
    user.is_active = True
    user.set_password(ADMIN_PASSWORD)
    db.session.commit()
    return created


def ensure_demo_users() -> int:
    """Create only a demo customer and the service administrator.

    No demo USER request is created intentionally: after login the customer
    sees the same empty "Мои заявки" state as a newly registered real user and
    can create the first request themselves.
    """
    created = 0
    user = User.query.filter_by(email="customer@demo.local").first()
    if not user:
        user = User(email="customer@demo.local")
        db.session.add(user)
        created += 1
    user.full_name = "Демо Заказчик"
    user.account_role = "customer"
    user.organization_inn = DEMO_CUSTOMER_INN
    user.organization_name = "Демонстрационный заказчик"
    user.is_active = True
    user.set_password(DEMO_PASSWORD)
    db.session.commit()
    created += ensure_admin_user()
    return created
