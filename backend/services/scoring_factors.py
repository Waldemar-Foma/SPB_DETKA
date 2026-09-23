"""Субиндексы скоринга.

Каждая функция — независимая, принимает закупку и контрагента,
возвращает целое число 0..100. Пороги берутся из scoring_config,
поэтому изменение модели не требует правок здесь.
"""

from __future__ import annotations

from backend.models import Procurement, Supplier
from . import scoring_config as cfg


def okpd2_score(procurement: Procurement, supplier: Supplier) -> int:
    """Совпадение классификатора ОКПД2.

    Логика:
      * точное совпадение кода — 100 баллов;
      * совпадение класса (первые 2 цифры) — 70 баллов;
      * иначе — 0.
    """
    if not supplier.okpd2_codes:
        return cfg.OKPD2_NONE_SCORE

    codes = {c.strip() for c in supplier.okpd2_codes.split(",") if c.strip()}
    if procurement.okpd2_code in codes:
        return cfg.OKPD2_EXACT_SCORE

    prefix = procurement.okpd2_code[:2]
    if any(c.startswith(prefix) for c in codes):
        return cfg.OKPD2_CLASS_SCORE

    return cfg.OKPD2_NONE_SCORE


def product_score(procurement: Procurement, supplier: Supplier) -> int:
    """Семантическая близость продукции.

    Полноценная ML-модель подключается в semantic.product_similarity().
    Здесь — весовой fallback: если модуль семантики вернул None,
    используем простую эвристику по ключевым словам.
    """
    from . import semantic  # локальный импорт: не тянем модель при старте

    similarity = semantic.product_similarity(procurement, supplier)
    if similarity is not None:
        return round(similarity * 100)

    # Fallback-эвристика: пересечение ключевых слов закупки и типа компании.
    procurement_keywords = _split_keywords(procurement.keywords)
    supplier_text = f"{supplier.name} {supplier.company_type}".lower()
    hits = sum(1 for kw in procurement_keywords if kw in supplier_text)

    if not procurement_keywords:
        return 40
    return min(100, 40 + hits * 20)


def experience_score(procurement: Procurement, supplier: Supplier) -> int:
    """Опыт аналогичных контрактов.

    Пороги заданы в scoring_config.EXPERIENCE_STEPS. Компания с 20+
    контрактами получает почти максимум — 94 (оставляем запас до 100,
    потому что «идеальных» совпадений не бывает).
    """
    count = len(supplier.contracts or [])
    for threshold, score in cfg.EXPERIENCE_STEPS:
        if count >= threshold:
            return score
    return 0


def region_score(procurement: Procurement, supplier: Supplier) -> int:
    """Региональное соответствие."""
    if procurement.region == supplier.region:
        return cfg.REGION_MATCH_SCORE
    return cfg.REGION_MISMATCH_SCORE


def scale_score(procurement: Procurement, supplier: Supplier) -> int:
    """Масштаб бизнеса относительно НМЦК.

    Считаем отношение годовой выручки к начальной цене закупки.
    Компания, чья выручка в 10 раз больше НМЦК, получает 100 —
    она точно справится с объёмом.
    """
    revenue = supplier.revenue_annual
    initial = procurement.initial_price

    if not revenue or not initial:
        return cfg.SCALE_FALLBACK_SCORE

    ratio = float(revenue) / float(initial)
    for threshold, score in cfg.SCALE_STEPS:
        if ratio >= threshold:
            return score
    return cfg.SCALE_STEPS[-1][1]


def _split_keywords(raw: str | None) -> list[str]:
    """Разбирает CSV-строку ключевых слов в список непустых токенов."""
    if not raw:
        return []
    return [kw.strip().lower() for kw in raw.split(",") if kw.strip()]