"""Персональное объяснение рекомендации на фактах, без галлюцинаций.

Qwen не участвует в выборе исполнителя: она получает уже рассчитанные метрики и
превращает их в понятный текст. Для разных компаний ей передаются разные
доказательства и разные стилистические инструкции, чтобы объяснения не звучали
как одна и та же заготовка. Если модель недоступна или выдаёт мусор, работает
детерминированный fallback.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import OrderedDict

from .geography import logistics_score
from .local_ai import chat
from .reputation import review_summary, workload_summary
from .role_classifier import classify_role, role_reason

SYSTEM_PROMPT = """Ты аналитик сервиса подбора контрагентов для заказчика.
Объясни, почему КОНКРЕТНАЯ компания попала в рекомендации для КОНКРЕТНОЙ заявки.
Пиши строго по-русски, обычной кириллицей. Не используй японские, китайские,
корейские и другие посторонние символы.

Требования к ответу:
- 3–5 предложений, ориентир 60–110 слов, без markdown и списков;
- текст должен быть персональным, а не шаблонным;
- используй writing_style из JSON как композиционную подсказку и НЕ начинай все
  ответы одинаково;
- сначала свяжи предмет заявки с реальным профилем/историей компании;
- приведи 2–3 конкретных факта: релевантные прошлые поставки/работы, победы,
  win rate, опыт с этим заказчиком, отзывы, ОКПД2;
- отдельно обозначь один практический нюанс: логистика, нагрузка или нехватка
  данных;
- если данных нет, честно скажи об этом;
- similarity и score — это показатели совпадения, а не вероятность успеха;
- не перечисляй все метрики подряд: объясняй человеческим языком.

Запрещено:
- придумывать контакты, склады, сертификаты, мощности, финансовые риски,
  отзывы или факты, которых нет в JSON;
- называть компанию «лучшей», «идеальной», «гарантированно надёжной»;
- объявлять победителя;
- писать канцелярские клише вроде «высокий рейтинг в категории исполнений»;
- копировать один и тот же порядок фраз для разных компаний.

Используй только факты из JSON."""

_REPAIR_PROMPT = """Перепиши текст строго на русском языке кириллицей.
Убери японские, китайские, корейские и любые другие посторонние письменности.
Сохрани только факты из исходного JSON. Сделай 3–5 естественных предложений,
без markdown, без шаблонных клише и без придумывания новых фактов."""

_STYLE_HINTS = (
    "Начни с того, что именно в специализации компании совпадает с предметом заявки; затем подкрепи это статистикой и закончи практическим нюансом.",
    "Начни с одного сильного факта из истории закупок компании; затем объясни смысловое соответствие заявке и только потом логистику или нагрузку.",
    "Сначала кратко объясни причину попадания компании в топ, затем сопоставь прошлые работы с текущей потребностью и обозначь ограничение данных.",
    "Начни с релевантного примера прошлой поставки или работы, если он есть; после него дай статистику, отзывы и практический вывод.",
    "Построй текст через баланс плюсов и оговорок: сначала два факта в пользу компании, затем один фактор, который заказчику стоит уточнить до контакта.",
)

_EXPLANATION_CACHE: OrderedDict[str, dict] = OrderedDict()
_CACHE_MAX = 512


def _short(value: str | None, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _tokens(*values: str | None) -> set[str]:
    text = " ".join(str(v or "") for v in values).lower()
    return {x for x in re.findall(r"[а-яёa-z0-9]+", text) if len(x) >= 4}


def _style_for(procurement, supplier) -> dict:
    raw = f"{getattr(procurement, 'procurement_number', '')}|{getattr(supplier, 'inn', '')}".encode("utf-8")
    variant = int(hashlib.sha1(raw).hexdigest()[:8], 16) % len(_STYLE_HINTS)
    return {"variant": variant + 1, "instruction": _STYLE_HINTS[variant]}


def _relevant_contracts(procurement, supplier, limit: int = 2) -> list[dict]:
    query_tokens = _tokens(
        getattr(procurement, "title", ""),
        getattr(procurement, "subject", ""),
        getattr(procurement, "keywords", ""),
        getattr(procurement, "okpd2_name", ""),
    )
    target_okpd = re.sub(r"\D", "", str(getattr(procurement, "okpd2_code", "") or ""))
    rows = []
    for contract in (getattr(supplier, "contracts", None) or []):
        subject = _short(getattr(contract, "subject", None) or getattr(contract, "product_name", None), 260)
        if not subject:
            continue
        subject_tokens = _tokens(subject)
        overlap = len(query_tokens & subject_tokens)
        code = str(getattr(contract, "okpd2_code", "") or "")
        code_clean = re.sub(r"\D", "", code)
        okpd_bonus = 0
        if target_okpd and code_clean:
            if code_clean == target_okpd:
                okpd_bonus = 6
            elif len(target_okpd) >= 4 and code_clean[:4] == target_okpd[:4]:
                okpd_bonus = 4
            elif len(target_okpd) >= 2 and code_clean[:2] == target_okpd[:2]:
                okpd_bonus = 2
        winner_bonus = 1 if bool(getattr(contract, "is_winner", True)) else 0
        score = overlap * 3 + okpd_bonus + winner_bonus
        rows.append((score, int(getattr(contract, "year", 0) or 0), {
            "subject": subject,
            "okpd2": code or None,
            "year": getattr(contract, "year", None),
            "winner": bool(getattr(contract, "is_winner", True)),
        }))
    rows.sort(key=lambda x: (x[0], x[1]), reverse=True)
    # Даже если текстового overlap нет, последние исторические победы полезнее,
    # чем пустой блок: Qwen увидит их как контекст, но не должна объявлять их
    # релевантными без других сигналов.
    return [item for _, _, item in rows[:limit]]


def _review_samples(supplier, limit: int = 1) -> list[dict]:
    reviews = sorted(
        (getattr(supplier, "reviews", None) or []),
        key=lambda r: getattr(r, "created_at", None) or 0,
        reverse=True,
    )
    out = []
    for review in reviews:
        comment = _short(getattr(review, "comment", None), 240)
        if not comment:
            continue
        out.append({"rating": getattr(review, "rating", None), "comment": comment})
        if len(out) >= limit:
            break
    return out


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
        "writing_style": _style_for(procurement, supplier),
        "request": {
            "title": _short(getattr(procurement, "title", ""), 240),
            "subject": _short(getattr(procurement, "subject", ""), 800),
            "keywords": _short(getattr(procurement, "keywords", ""), 350),
            "okpd2": getattr(procurement, "okpd2_code", None),
            "delivery_region": getattr(procurement, "delivery_region", None) or getattr(procurement, "region", None),
        },
        "supplier": {
            "name": _short(getattr(supplier, "name", ""), 240),
            "inn": getattr(supplier, "inn", None),
            "region": getattr(supplier, "region", None),
            "specialization": _short(getattr(supplier, "specialization", ""), 520),
            "okpd2_codes": [x.strip() for x in str(getattr(supplier, "okpd2_codes", "") or "").split(",") if x.strip()][:10],
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
            "relevant_examples": _relevant_contracts(procurement, supplier),
        },
        "reviews": {
            "internal_rating": reviews["avg"],
            "internal_reviews_count": reviews["count"],
            "examples": _review_samples(supplier),
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
        max_tokens=280,
        temperature=0.52,
    )
    text = _normalize_text(raw)

    if text and not _valid_generated_text(text):
        repaired = chat(
            _REPAIR_PROMPT,
            json.dumps({"facts": facts, "bad_text": text}, ensure_ascii=False),
            max_tokens=250,
            temperature=0.15,
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
        str(facts["writing_style"]["variant"]),
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
    if len(text) < 160:
        return False
    if _contains_forbidden_script(text):
        return False
    lowered = text.lower()
    banned_phrases = (
        "высокий рейтинг в категории исполнений",
        "компания подходит как дистрибьютор / оптовик с высоким рейтингом",
        "идеальная логистика",
    )
    if any(x in lowered for x in banned_phrases):
        return False
    if "гарантирован" in lowered:
        return False
    # Ответ из одной длинной фразы тоже считаем неудачным.
    if len(re.findall(r"[.!?](?:\s|$)", text)) < 3:
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
    variant = int(facts.get("writing_style", {}).get("variant") or 1)

    examples = history.get("relevant_examples") or []
    example = examples[0]["subject"] if examples else None
    wr = f"{history['win_rate_percent']}%" if history["win_rate_percent"] is not None else None

    match_sentence = (
        f"Профиль компании хорошо пересекается с предметом заявки: смысловое совпадение составляет {match['semantic_match']}%, "
        f"а показатель опыта в нужной категории — {match['category_experience']}%."
    )
    history_sentence = (
        f"В закупочной истории зафиксировано {history['wins']} побед при {history['participations']} участиях"
        + (f", поэтому фактический win rate составляет {wr}." if wr else ".")
    ) if history["participations"] else "По истории участий и побед пока недостаточно данных для отдельного вывода."
    example_sentence = f"Среди прошлых работ есть близкий по смыслу пример: «{example}»." if example else (
        f"Специализация в базе описана как «{supplier['specialization'][:180]}»." if supplier.get("specialization") else
        "Подробных примеров прошлых работ в локальной базе пока немного, поэтому профиль стоит дополнительно уточнить при контакте."
    )
    review_sentence = (
        f"Внутри сервиса у компании {reviews['internal_reviews_count']} отзыв(а/ов) со средней оценкой {reviews['internal_rating']}/5."
        if reviews["internal_reviews_count"] else
        "Отзывов от пользователей сервиса пока нет, поэтому этот фактор не усиливает и не ослабляет рекомендацию."
    )
    logistics_sentence = logistics.get("note") or "По логистике недостаточно данных для уверенного вывода."
    if workload.get("warning"):
        nuance_sentence = workload["warning"]
    elif workload.get("active_requests_in_service") == 0:
        nuance_sentence = "Сервис не видит полной загрузки компании вне собственных заявок, поэтому доступность ресурсов лучше уточнить напрямую."
    else:
        nuance_sentence = "По текущей нагрузке внутри сервиса критического сигнала нет, но внешнюю загрузку компания не раскрывает."

    orders = {
        1: [match_sentence, example_sentence, history_sentence, review_sentence, logistics_sentence, nuance_sentence],
        2: [history_sentence, match_sentence, example_sentence, logistics_sentence, review_sentence, nuance_sentence],
        3: [match_sentence, history_sentence, review_sentence, example_sentence, nuance_sentence, logistics_sentence],
        4: [example_sentence, match_sentence, history_sentence, review_sentence, logistics_sentence, nuance_sentence],
        5: [match_sentence, example_sentence, logistics_sentence, history_sentence, review_sentence, nuance_sentence],
    }
    return " ".join(orders.get(variant, orders[1])[:5])
