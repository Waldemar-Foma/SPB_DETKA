"""Субиндексы матчинга, каждый в диапазоне 0..100."""
from __future__ import annotations

import re

from . import scoring_config as cfg
from .geography import logistics_score
from .reputation import review_summary, workload_summary


def _codes(raw: str | None) -> set[str]:
    return {x.strip() for x in (raw or "").split(",") if x.strip()}


def okpd2_score(procurement, supplier) -> int:
    target = (procurement.okpd2_code or "").strip()
    if not target or target.upper() == "AUTO":
        return 60  # нейтрально: заявка создана свободным текстом без явного ОКПД2
    codes = _codes(supplier.okpd2_codes)
    if not codes:
        return 0
    if target in codes:
        return cfg.OKPD2_EXACT_SCORE
    norm = re.sub(r"\D", "", target)
    for code in codes:
        c = re.sub(r"\D", "", code)
        if norm[:4] and c[:4] == norm[:4]:
            return cfg.OKPD2_GROUP_SCORE
    if norm[:2] and any(re.sub(r"\D", "", c).startswith(norm[:2]) for c in codes):
        return cfg.OKPD2_CLASS_SCORE
    return 0


def product_score(procurement, supplier) -> int:
    from .semantic import product_similarity

    similarity = product_similarity(procurement, supplier)
    if similarity is not None:
        return round(similarity * 100)

    a = _tokens(" ".join(str(x or "") for x in [procurement.title, procurement.subject, procurement.okpd2_name, procurement.keywords]))
    b = _tokens(" ".join(str(x or "") for x in [supplier.name, getattr(supplier, "specialization", ""), supplier.okpd2_codes]))
    if not a or not b:
        return 30
    overlap = len(a & b)
    j = overlap / max(1, len(a | b))
    return max(20, min(100, round(25 + j * 170 + min(overlap, 4) * 8)))


def experience_score(procurement, supplier) -> int:
    target = re.sub(r"\D", "", procurement.okpd2_code or "")[:2]
    related = 0
    for c in (supplier.contracts or []):
        if not bool(getattr(c, "is_winner", True)):
            continue
        code = re.sub(r"\D", "", (getattr(c, "okpd2_code", None) or ""))
        if target and code.startswith(target):
            related += 1
    count = related if target else int(getattr(supplier, "wins_count", 0) or 0)
    if count >= 20: return 100
    if count >= 10: return 88
    if count >= 5: return 75
    if count >= 2: return 55
    if count >= 1: return 38
    return 15 if int(getattr(supplier, "participation_count", 0) or 0) else 0


def win_rate_score(_procurement, supplier) -> int:
    participations = int(getattr(supplier, "participation_count", 0) or 0)
    wins = int(getattr(supplier, "wins_count", 0) or 0)
    if participations <= 0:
        return 35
    rate = wins / participations
    # 35%+ побед в госзакупках уже считается сильным историческим сигналом;
    # не требуем нереалистичных 100% для максимального балла.
    return max(5, min(100, round(rate / 0.35 * 100)))


def customer_history_score(procurement, supplier) -> int:
    customer = getattr(procurement, "customer_inn", None)
    if not customer:
        return 50
    count = sum(
        1 for c in (supplier.contracts or [])
        if bool(getattr(c, "is_winner", True)) and getattr(c, "customer_inn", None) == customer
    )
    if count >= 5: return 100
    if count >= 3: return 85
    if count >= 1: return 68
    return 35


def geography_score(procurement, supplier) -> int:
    return int(logistics_score(procurement, supplier)["score"])


def reviews_score(_procurement, supplier) -> int:
    summary = review_summary(supplier.id)
    if summary["count"] == 0:
        return 60  # отсутствие внутренних отзывов — не негативный факт
    # 1..5 -> 20..100; небольшое доверие к выборке появляется после 3 отзывов.
    base = int((summary["avg"] or 3) * 20)
    confidence = min(1.0, summary["count"] / 3)
    return round(60 * (1 - confidence) + base * confidence)


def workload_score(_procurement, supplier) -> int:
    info = workload_summary(supplier.inn)
    active = info["active_requests"]
    if active >= 5: return 25
    if active >= 3: return 50
    if active >= 1: return 75
    return 85  # это не доказательство отсутствия загрузки вне сервиса


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[а-яёa-z0-9]+", (text or "").lower()) if len(t) >= 4}
