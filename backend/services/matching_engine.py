"""Взвешенный расчёт релевантности и объяснимые пользовательские метрики."""
from __future__ import annotations

from . import scoring_config as cfg
from . import scoring_factors as sf
from .geography import logistics_score
from .reputation import review_summary, workload_summary
from .role_classifier import classify_role


def compute_score(procurement, supplier, preference: str = "balanced") -> dict:
    factors = {
        "product": sf.product_score(procurement, supplier),
        "okpd2": sf.okpd2_score(procurement, supplier),
        "experience": sf.experience_score(procurement, supplier),
        "win_rate": sf.win_rate_score(procurement, supplier),
        "customer": sf.customer_history_score(procurement, supplier),
        "geography": sf.geography_score(procurement, supplier),
        "reviews": sf.reviews_score(procurement, supplier),
        "workload": sf.workload_score(procurement, supplier),
    }
    weights = cfg.get_weights(preference)
    total = round(sum(factors[k] * weights[k] for k in weights))
    return {"total": max(0, min(100, total)), **factors, "weights": weights}


def relevance_label(score: int) -> str:
    for threshold, label in cfg.RELEVANCE_THRESHOLDS:
        if score >= threshold:
            return label
    return cfg.RELEVANCE_THRESHOLDS[-1][1]


def build_tags(procurement, supplier, scores: dict) -> list[str]:
    tags: list[str] = []
    role = classify_role(supplier, procurement)
    if scores["product"] >= 80:
        tags.append("Сильное совпадение по смыслу")
    if scores["okpd2"] >= 85:
        tags.append("Совпадает ОКПД2")
    if int(getattr(supplier, "wins_count", 0) or 0):
        tags.append(f"{int(supplier.wins_count)} побед в истории")
    if bool(getattr(supplier, "is_gisp_manufacturer", False)):
        tags.append("Производитель ГИСП")
    geo = logistics_score(procurement, supplier)
    if geo["score"] >= 80:
        tags.append("Логистика выглядит разумно")
    reviews = review_summary(supplier.id)
    if reviews["count"]:
        tags.append(f"Отзывы {reviews['avg']}/5")
    workload = workload_summary(supplier.inn)
    if workload["level"] == "high":
        tags.append("Возможна высокая загрузка")
    if role == "Исполнитель / Подрядчик":
        tags.append("Подходит для услуг / работ")
    return tags[:5]
