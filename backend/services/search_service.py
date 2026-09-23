"""Фильтрация, сортировка и пагинация результатов матчинга."""

from __future__ import annotations

from typing import Any, Iterable

DEFAULT_LIMIT = 20
MAX_LIMIT = 100

SORT_KEYS = {
    "relevance_desc": lambda x: -x["score"],
    "relevance_asc":  lambda x:  x["score"],
    "contracts_desc": lambda x: -x["contracts_count"],
    "revenue_desc":   lambda x: -x["revenue_mrd"],
    "name_asc":       lambda x:  x["name"].lower(),
}


def filter_and_sort(
    items: Iterable[dict],
    filters: dict[str, Any],
    sort_key: str,
) -> list[dict]:
    """Применяет фильтры и сортировку к списку карточек."""
    result = [item for item in items if _matches(item, filters)]
    result.sort(key=SORT_KEYS.get(sort_key, SORT_KEYS["relevance_desc"]))
    return result


def paginate(
    items: list[dict],
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> dict:
    """Возвращает срез с мета-блоком для клиента.

    Клиент использует meta.has_more, чтобы решать, показывать ли
    кнопку «Показать ещё».
    """
    limit = max(1, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))
    window = items[offset: offset + limit]

    return {
        "items": window,
        "meta": {
            "total": len(items),
            "limit": limit,
            "offset": offset,
            "returned": len(window),
            "has_more": offset + len(window) < len(items),
        },
    }


def _matches(item: dict, filters: dict[str, Any]) -> bool:
    """Проверяет, проходит ли карточка все активные фильтры."""
    if filters.get("company_type") and item["company_type"] != filters["company_type"]:
        return False
    if filters.get("region") and item["region"] != filters["region"]:
        return False
    if filters.get("min_experience"):
        if (item["years_on_market"] or 0) < int(filters["min_experience"]):
            return False
    if filters.get("min_revenue"):
        if item["revenue_mrd"] * 1e9 < float(filters["min_revenue"]):
            return False
    if filters.get("q"):
        query = filters["q"].lower()
        haystack = f"{item['name']} {item['inn']}".lower()
        if query not in haystack:
            return False
    return True