"""Аналитика по базе контрагентов.

Контракт функций фиксирован: каждая возвращает dict или list[dict],
готовый к jsonify. Сейчас функции не реализованы — это точки
расширения для страницы «Аналитика» в сайдбаре.
"""

from __future__ import annotations

from backend.models import Supplier


def by_region() -> list[dict]:
    """Распределение контрагентов по регионам.

    Ожидаемый формат ответа:
        [{"region": "Санкт-Петербург", "count": 24}, ...]
    """
    raise NotImplementedError("Analytics: by_region")


def by_company_type() -> list[dict]:
    """Распределение по типам компаний.

    Ожидаемый формат:
        [{"company_type": "Производитель", "count": 12}, ...]
    """
    raise NotImplementedError("Analytics: by_company_type")


def by_revenue_bucket() -> list[dict]:
    """Распределение по диапазонам выручки.

    Ожидаемый формат:
        [{"bucket": "50–300 млн", "count": 15}, ...]
    """
    raise NotImplementedError("Analytics: by_revenue_bucket")


def top_by_contracts(limit: int = 10) -> list[dict]:
    """Топ компаний по количеству контрактов."""
    raise NotImplementedError("Analytics: top_by_contracts")