"""Прозрачная классификация роли контрагента.

Правила соответствуют хакатонной гипотезе проекта и не зависят от генеративной
модели: роль должна быть воспроизводимой и объяснимой.
"""
from __future__ import annotations

import re

GOODS_HINTS = ("поставка", "товар", "оборудован", "продукт", "издел", "материал")
SERVICE_HINTS = ("услуг", "обслуживан", "ремонт", "аренд", "перевоз", "обучен")
WORK_HINTS = ("работ", "строит", "монтаж", "реконструк", "благоустрой")


def procurement_kind(procurement) -> str:
    explicit = (getattr(procurement, "procurement_kind", None) or "").strip().lower()
    if explicit in {"goods", "services", "works"}:
        return explicit

    text = " ".join(
        str(x or "") for x in [
            getattr(procurement, "title", ""),
            getattr(procurement, "okpd2_name", ""),
            getattr(procurement, "keywords", ""),
        ]
    ).lower()
    if any(x in text for x in WORK_HINTS):
        return "works"
    if any(x in text for x in SERVICE_HINTS):
        return "services"
    if any(x in text for x in GOODS_HINTS):
        return "goods"

    # Классы 01–32 в ОКПД2 преимущественно относятся к продукции/товарам.
    code = (getattr(procurement, "okpd2_code", "") or "").strip()
    m = re.match(r"(\d{2})", code)
    if m and int(m.group(1)) <= 32:
        return "goods"
    return "services"


def classify_role(supplier, procurement=None) -> str:
    if bool(getattr(supplier, "is_gisp_manufacturer", False)):
        return "Производитель"

    kind = procurement_kind(procurement) if procurement is not None else None
    okved = (getattr(supplier, "primary_okved", None) or "").strip()

    if kind in {"services", "works"}:
        return "Исполнитель / Подрядчик"

    if okved.startswith("46") or is_large_distributor(supplier):
        return "Дистрибьютор / Оптовик"

    # Для старых demo-записей сохраняем ранее заданную роль, если она полезна.
    legacy = (getattr(supplier, "company_type", None) or "").strip()
    if legacy in {"Производитель", "Дистрибьютор", "Дистрибьютор / Оптовик"}:
        return "Дистрибьютор / Оптовик" if legacy.startswith("Дистрибьютор") else legacy

    return "Поставщик"


def is_large_distributor(supplier) -> bool:
    if bool(getattr(supplier, "is_gisp_manufacturer", False)):
        return False
    wins = int(getattr(supplier, "wins_count", 0) or 0)
    diversity = int(getattr(supplier, "unique_won_okpd2", 0) or 0)
    return wins >= 20 and diversity >= 10


def role_reason(supplier, procurement=None) -> str:
    role = classify_role(supplier, procurement)
    if role == "Производитель":
        return "ИНН найден в локально загруженном реестре ГИСП/Минпромторга."
    if role == "Исполнитель / Подрядчик":
        return "Предмет закупки относится к услугам/работам; роль определена контекстно."
    if role == "Дистрибьютор / Оптовик":
        if (getattr(supplier, "primary_okved", None) or "").startswith("46"):
            return "Компания не отмечена как производитель, основной ОКВЭД относится к оптовой торговле 46.xx."
        return "Тип выведен из реальной истории закупок: много побед по разным группам ОКПД2 при отсутствии признака производителя ГИСП."
    return "Компания поставляет товары и не попала под правила производителя или оптовика."
