"""Проверка доступных локальных признаков контрагента.

Важно: модуль не имитирует ФНС, ФССП или арбитраж. Пока соответствующие
офлайн-источники не подключены, интерфейс честно показывает их как
«не подключено».
"""
from __future__ import annotations

import re

from flask import Blueprint, render_template, request

from backend.models import Supplier, SupplierReview
from backend.services.auth import current_user, login_required
from backend.services.reputation import review_summary
from backend.blueprints.suppliers import registry_role

bp = Blueprint("security", __name__, url_prefix="/security")


def _clean_inn(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _build_checks(supplier: Supplier) -> list[dict]:
    contacts = [supplier.address, supplier.phone, supplier.email, supplier.website]
    return [
        {
            "name": "Компания есть в локальном реестре",
            "status": "ok",
            "value": f"Источник: {supplier.data_source or 'не указан'}",
            "source": "Локальная БД",
        },
        {
            "name": "Регион",
            "status": "ok" if supplier.region else "neutral",
            "value": supplier.region or "не указан",
            "source": "KPP / профиль",
        },
        {
            "name": "ГИСП / Минпромторг",
            "status": "ok" if supplier.is_gisp_manufacturer else "neutral",
            "value": "Производитель подтверждён" if supplier.is_gisp_manufacturer else "Совпадение производителя не найдено",
            "source": "ГИСП (если синхронизация запускалась)",
        },
        {
            "name": "Основной ОКВЭД",
            "status": "ok" if supplier.primary_okved else "warn",
            "value": supplier.primary_okved or "Нет данных",
            "source": "Офлайн-обогащение",
        },
        {
            "name": "МСП",
            "status": "ok" if supplier.is_sme else "neutral",
            "value": "Есть признак МСП" if supplier.is_sme else "Нет признака / данные не загружены",
            "source": "Офлайн-обогащение",
        },
        {
            "name": "Контактные данные",
            "status": "ok" if sum(bool(x) for x in contacts) >= 2 else "warn",
            "value": f"Заполнено {sum(bool(x) for x in contacts)} из 4 полей",
            "source": "Профиль компании",
        },
        {
            "name": "История участия",
            "status": "ok" if supplier.participation_count else "neutral",
            "value": f"Участий: {supplier.participation_count}; побед: {supplier.wins_count}",
            "source": "Датасет закупок",
        },
        {"name": "ФНС: статус юрлица / задолженность", "status": "offline", "value": "Источник пока не подключён", "source": "ФНС"},
        {"name": "ФССП: исполнительные производства", "status": "offline", "value": "Источник пока не подключён", "source": "ФССП"},
        {"name": "Арбитражные дела", "status": "offline", "value": "Источник пока не подключён", "source": "КАД Арбитр"},
    ]


@bp.get("/")
@login_required
def page():
    user = current_user()
    requested = _clean_inn(request.args.get("inn", ""))
    default_inn = ""
    inn = requested or default_inn
    supplier = Supplier.query.filter_by(inn=inn).first() if inn else None
    checks = _build_checks(supplier) if supplier else []
    data_completeness = 0
    reviews = []
    reviews_summary = {"avg": None, "count": 0, "quality": None, "deadlines": None, "communication": None}
    if supplier:
        fields = [supplier.name, supplier.region, supplier.specialization, supplier.okpd2_codes, supplier.primary_okved, supplier.address, supplier.email, supplier.phone]
        data_completeness = round(sum(bool(x) for x in fields) / len(fields) * 100)
        reviews_summary = review_summary(supplier.id)
        reviews = (
            SupplierReview.query
            .filter_by(supplier_id=supplier.id)
            .order_by(SupplierReview.created_at.desc())
            .limit(30)
            .all()
        )

    return render_template(
        "pages/security.html",
        page_id="security",
        page_title="Проверка СБ",
        user=user,
        requested_inn=inn,
        supplier=supplier,
        checks=checks,
        data_completeness=data_completeness,
        registry_role=registry_role(supplier) if supplier else None,
        reviews=reviews,
        reviews_summary=reviews_summary,
    )
