"""Понятное объяснение рекомендации на фактах, без галлюцинаций.

Qwen используется только как слой объяснимости. Если локальная модель недоступна,
ответ содержит запрещённые письменности или выглядит слишком коротким/пустым,
показывается детерминированное объяснение по тем же фактам.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import OrderedDict

from .geography import logistics_score
from .local_ai import chat
from .reputation import review_summary, workload_summary
from .role_classifier import classify_role, role_reason

SYSTEM_PROMPT = """Ты аналитик сервиса подбора контрагентов для заказчика.
Сформируй персональное объяснение именно для ЭТОЙ компании и ЭТОЙ заявки.
Пиши строго по-русски, обычной кириллицей, без японских, китайских, корейских и других посторонних символов.
Формат: 3–5 предложений, примерно 60–110 слов, без markdown и списков.

Обязательно:
1) начни с конкретного соответствия запросу: профиль/специализация, смысловое совпадение или опыт в категории;
2) приведи 1–2 подтверждающих факта из истории: победы, win rate, отзывы, опыт с этим заказчиком;
3) отдельно оцени логистику и нагрузку, только если для них есть данные;
4) если данных нет, прямо скажи «данных пока нет», а не додумывай.

Запрещено:
- придумывать контакты, сертификаты, склады, финансовые риски, отзывы или причины, которых нет в JSON;
- называть компанию «лучшей», «идеальной», «гарантированно надёжной» или объявлять победителем;
- использовать шаблонные фразы вроде «высокий рейтинг в категории исполнений»;
- выдавать similarity/score за вероятность успеха.

Используй только факты из JSON. Числа округляй естественно и не перегружай текст метриками."""

_REPAIR_PROMPT = """Перепиши текст строго на русском языке кириллицей.
Не используй японские, китайские, корейские и другие посторонние письменности.
Сохрани только факты из исходного JSON. 3–5 предложений, без markdown."""

_EXPLANATION_CACHE: OrderedDict[str, dict] = OrderedDict()
_CACHE_MAX = 512


def _short(value: str | None, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def build_facts(procurement, supplier, scores: dict, role: str | None = None) -> dict:
    reviews = review_summary(supplier.id)
    workload = workload_summary(supplier.inn)
    geo = logistics_score(procurement, supplier)
    participations = int(getattr(supplier, "participation_count", 0) or 0)
    wins = int(getattr(supplier, "wins_count", 0) or 0)
    win_rate = round(wins / participations * 100, 1) if participations else None
    same_customer = sum(
        1 for c in (getattr(supplier, "contracts", None) or [])
        if bool(getattr(c, "is_winner", True))
        and getattr(procurement, "customer_inn", None)
        and getattr(c, "customer_inn", None) == getattr(procurement, "customer_inn", None)
    )
    selected_role = role or classify_role(supplier, procurement)
    return {
        "request": {
            "title": _short(getattr(procurement, "title", ""), 240),
            "subject": _short(getattr(procurement, "subject", ""), 650),
            "keywords": _short(getattr(procurement, "keywords", ""), 300),
            "okpd2": getattr(procurement, "okpd2_code", None),
            "delivery_region": getattr(procurement, "delivery_region", None) or getattr(procurement, "region", None),
        },
        "supplier": {
            "name": _short(getattr(supplier, "name", ""), 240),
            "inn": getattr(supplier, "inn", None),
            "region": getattr(supplier, "region", None),
            "specialization": _short(getattr(supplier, "specialization", ""), 650),
            "okpd2_codes": [x.strip() for x in str(getattr(supplier, "okpd2_codes", "") or "").split(",") if x.strip()][:8],
            "classification": selected_role,
            "classification_reason": role_reason(supplier, procurement),
            "is_gisp_manufacturer": bool(getattr(supplier, "is_gisp_manufacturer", False)),
        },
        "match": {
            "overall_score": scores.get("total", 0),
            "semantic_match": scores.get("product", 0),
            "category_experience": scores.get("experience", 0),
            "okpd2_match": scores.get("okpd2", 0),
        },
        "history": {
            "participations": participations,
            "wins": wins,
            "win_rate_percent": win_rate,
            "same_customer_wins": same_customer,
        },
        "reviews": {
            "internal_rating": reviews["avg"],
            "internal_reviews_count": reviews["count"],
        },
        "logistics": {
            "distance_km": geo["distance_km"],
            "score": geo["score"],
            "note": geo["note"],
        },
        "workload": {
            "active_requests_in_service": workload["active_requests"],
            "label": workload["label"],
            "warning": workload["warning"],
        },
    }


def explain(procurement, supplier, scores: dict, role: str | None = None) -> dict:
    facts = build_facts(procurement, supplier, scores, role)
    cache_key = _cache_key(procurement, supplier, facts)
    cached = _EXPLANATION_CACHE.get(cache_key)
    if cached is not None:
        _EXPLANATION_CACHE.move_to_end(cache_key)
        return cached

    raw = chat(
        SYSTEM_PROMPT,
        json.dumps(facts, ensure_ascii=False, separators=(",", ":")),
        max_tokens=220,
        temperature=0.18,
    )
    text = _normalize_text(raw)

    # Маленькая локальная модель иногда смешивает кириллицу с чужими письменностями.
    # Такой ответ нельзя показывать пользователю. Один раз просим переписать, затем
    # безопасно уходим в детерминированный fallback.
    if text and not _valid_generated_text(text):
        repaired = chat(
            _REPAIR_PROMPT,
            json.dumps({"facts": facts, "bad_text": text}, ensure_ascii=False),
            max_tokens=220,
            temperature=0.05,
        )
        text = _normalize_text(repaired)

    if text and _valid_generated_text(text):
        result = {"text": text, "facts": facts, "source": "qwen2.5:3b"}
    else:
        result = {"text": _fallback(facts), "facts": facts, "source": "rules"}

    _EXPLANATION_CACHE[cache_key] = result
    _EXPLANATION_CACHE.move_to_end(cache_key)
    while len(_EXPLANATION_CACHE) > _CACHE_MAX:
        _EXPLANATION_CACHE.popitem(last=False)
    return result


def _cache_key(procurement, supplier, facts: dict) -> str:
    return "|".join([
        str(getattr(procurement, "id", None) or getattr(procurement, "procurement_number", "")),
        str(getattr(procurement, "updated_at", "")),
        str(getattr(supplier, "id", None) or getattr(supplier, "inn", "")),
        str(facts["reviews"]["internal_reviews_count"]),
        str(facts["workload"]["active_requests_in_service"]),
    ])


def _normalize_text(text: str | None) -> str | None:
    if not text:
        return None
    value = unicodedata.normalize("NFKC", str(text))
    value = value.replace("\r", " ").replace("\n", " ")
    value = re.sub(r"\s+", " ", value).strip()
    value = value.strip(' "“”«»')
    return value or None


def _valid_generated_text(text: str) -> bool:
    if len(text) < 120:
        return False
    if _contains_forbidden_script(text):
        return False
    # Отсеиваем ответы, которые по сути повторяют старую однотипную фразу.
    lowered = text.lower()
    banned_phrases = (
        "высокий рейтинг в категории исполнений",
        "компания подходит как дистрибьютор / оптовик с высоким рейтингом",
    )
    if any(x in lowered for x in banned_phrases):
        return False
    if "идеаль" in lowered or "гарантирован" in lowered:
        return False
    return True


def _contains_forbidden_script(text: str) -> bool:
    """True, если модель подмешала чужую письменность в русский ответ."""
    for ch in text:
        if not ch.isalpha():
            continue
        name = unicodedata.name(ch, "")
        if "CYRILLIC" in name or "LATIN" in name:
            continue
        return True
    return False


def _fallback(facts: dict) -> str:
    match = facts["match"]
    history = facts["history"]
    reviews = facts["reviews"]
    logistics = facts["logistics"]
    workload = facts["workload"]
    supplier = facts["supplier"]

    parts: list[str] = []
    specialization = supplier.get("specialization")
    if specialization:
        parts.append(
            f"По профилю работ компания близка к вашей заявке: смысловое совпадение — {match['semantic_match']}%, "
            f"а опыт в нужной категории оценён в {match['category_experience']}%."
        )
    else:
        parts.append(
            f"Компания попала в топ по истории закупок и совпадению с запросом: по смыслу — {match['semantic_match']}%, "
            f"по опыту в категории — {match['category_experience']}%."
        )

    if history["participations"]:
        wr = f"{history['win_rate_percent']}%" if history["win_rate_percent"] is not None else "нет данных"
        parts.append(
            f"В базе у неё {history['wins']} побед при {history['participations']} участиях, win rate — {wr}."
        )
    else:
        parts.append("В нашей истории закупок пока недостаточно данных об участиях и победах этой компании.")

    if reviews["internal_reviews_count"]:
        parts.append(
            f"Пользователи сервиса оставили {reviews['internal_reviews_count']} отзыв(а/ов), средняя оценка — {reviews['internal_rating']}/5."
        )
    elif history["same_customer_wins"]:
        parts.append(f"Компания уже побеждала в {history['same_customer_wins']} закупке(ах) вашей организации.")

    caution_bits: list[str] = []
    if logistics.get("note"):
        caution_bits.append(logistics["note"])
    if workload.get("warning"):
        caution_bits.append(workload["warning"])
    elif workload.get("active_requests_in_service") == 0:
        caution_bits.append("По текущей загрузке вне нашего сервиса данных нет, поэтому свободные ресурсы лучше уточнить напрямую.")
    if caution_bits:
        parts.append(" ".join(caution_bits[:2]))

    return " ".join(parts[:4])
