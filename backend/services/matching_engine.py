"""Взвешенный расчёт итогового индекса релевантности."""

from __future__ import annotations

from backend.models import Procurement, Supplier
from . import scoring_config as cfg
from . import scoring_factors as sf


def compute_score(procurement: Procurement, supplier: Supplier) -> dict:
    """Возвращает разбивку по факторам и итоговый Score (0..100)."""
    factors = {
        "okpd2":      sf.okpd2_score(procurement, supplier),
        "product":    sf.product_score(procurement, supplier),
        "experience": sf.experience_score(procurement, supplier),
        "region":     sf.region_score(procurement, supplier),
        "scale":      sf.scale_score(procurement, supplier),
    }
    total = round(sum(factors[k] * cfg.WEIGHTS[k] for k in cfg.WEIGHTS))
    return {"total": total, **factors}


def relevance_label(score: int) -> str:
    """Текстовая интерпретация балла — по шкале из scoring_config."""
    for threshold, label in cfg.RELEVANCE_THRESHOLDS:
        if score >= threshold:
            return label
    return cfg.RELEVANCE_THRESHOLDS[-1][1]


def build_tags(procurement: Procurement, supplier: Supplier, scores: dict) -> list[str]:
    """Формирует информационные теги для карточки."""
    tags: list[str] = []

    if scores["okpd2"] == cfg.OKPD2_EXACT_SCORE:
        tags.append("ОКПД2 совпадает")
    elif scores["okpd2"] == cfg.OKPD2_CLASS_SCORE:
        tags.append("ОКПД2 по классу")

    count = len(supplier.contracts or [])
    if count:
        tags.append(f"{count} аналогичных контрактов")

    if supplier.website and supplier.phone:
        tags.append("Есть сайт и контакты")

    if not supplier.is_verified:
        tags.append("Требует верификации")

    return tags