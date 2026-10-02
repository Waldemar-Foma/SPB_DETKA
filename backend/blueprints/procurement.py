from __future__ import annotations

import re
from datetime import datetime

from flask import Blueprint, jsonify, request
from sqlalchemy.orm import selectinload

from backend.extensions import db
from backend.models import Procurement, Supplier
from backend.services.auth import customer_required, current_user
from backend.services.geography import logistics_score
from backend.services.matching_engine import build_tags, compute_score, relevance_label
from backend.services.reputation import review_summary, workload_summary, invalidate_workload_cache
from backend.services.request_lifecycle import touch
from backend.services.role_classifier import classify_role
from backend.services.semantic import warm_similarity_cache
from backend.services.candidate_retrieval import search_procurement

bp = Blueprint("procurement", __name__)

TOP_LIMIT = 5
ALLOWED_TYPES = {"Производитель", "Дистрибьютор / Оптовик", "Поставщик", "Исполнитель / Подрядчик"}


def _owned(procurement: Procurement) -> bool:
    user = current_user()
    if not user:
        return False
    return user.account_role == "admin" or procurement.customer_inn == user.organization_inn


@bp.get("/list")
def procurement_list():
    """Только пользовательские заявки текущего заказчика."""
    user = current_user()
    if not user:
        return jsonify({"items": []})
    query = Procurement.query.filter(
        Procurement.source_system == "USER",
        Procurement.deleted_at.is_(None),
    )
    if user.account_role != "admin":
        query = query.filter(Procurement.customer_inn == user.organization_inn)
    rows = query.order_by(Procurement.updated_at.desc(), Procurement.id.desc()).limit(200).all()
    return jsonify({"items": [{
        "procurement_id": p.procurement_number,
        "title": p.title,
        "okpd2": p.okpd2_code or "",
        "status": p.status,
        "selected_supplier_inn": p.selected_supplier_inn,
    } for p in rows]})


@bp.post("/analyze")
def analyze():
    query = (request.get_json(silent=True) or {}).get("query", "").strip()
    user = current_user()
    base = Procurement.query.filter(Procurement.source_system == "USER", Procurement.deleted_at.is_(None))
    if user and user.account_role != "admin":
        base = base.filter(Procurement.customer_inn == user.organization_inn)
    procurement = base.filter_by(procurement_number=query).first() if query else base.order_by(Procurement.updated_at.desc()).first()
    if not procurement:
        return jsonify({"error": {"code": "not_found", "message": "Заявка не найдена"}}), 404
    selected = Supplier.query.filter_by(inn=procurement.selected_supplier_inn).first() if procurement.selected_supplier_inn else None
    return jsonify({
        **procurement.to_dict(),
        "total_found": Supplier.query.count(),
        "selected_supplier_name": selected.name if selected else None,
        "selected_at": procurement.selected_at.isoformat() if procurement.selected_at else None,
    })


@bp.get("/<procurement_number>/suppliers")
def suppliers_for(procurement_number: str):
    procurement = Procurement.query.filter_by(procurement_number=procurement_number).first_or_404()
    if not _owned(procurement):
        return jsonify({"error": {"code": "forbidden", "message": "Заявка принадлежит другой организации"}}), 403
    if procurement.deleted_at is not None:
        return jsonify({"error": {"code": "request_deleted", "message": "Заявка удалена и больше недоступна для подбора"}}), 410
    if procurement.status not in {"matching", "selected"} or procurement.completed_at or procurement.archived_at:
        return jsonify({
            "error": {
                "code": "matching_closed",
                "message": "Подбор по этой заявке закрыт после завершения или архива заказа.",
            },
            "details_url": f"/contracts/{procurement.procurement_number}",
        }), 409

    requested_types = {
        x.strip() for x in (request.args.get("company_types") or "").split(",") if x.strip() in ALLOWED_TYPES
    }

    # 1) Первый этап — предоставленный пользователем all-minilm + FAISS.
    # Он быстро находит семантически близкий пул по истории поставок.
    retrieval = search_procurement(procurement, top_k=120)
    retrieval_by_inn = {x["inn"]: x for x in retrieval.get("items", [])}
    model_inns = list(retrieval_by_inn)

    candidates: list[Supplier] = []
    model_matched_count = 0
    used_fallback = False
    if retrieval.get("ok") and model_inns:
        loaded = Supplier.query.options(selectinload(Supplier.contracts)).filter(Supplier.inn.in_(model_inns)).all()
        by_inn = {s.inn: s for s in loaded}
        # Сохраняем порядок FAISS до комплексного re-ranking.
        candidates = [by_inn[inn] for inn in model_inns if inn in by_inn]
        model_matched_count = len(candidates)

    # DB-prefilter остаётся не только аварийным fallback. Даже при рабочем FAISS
    # добавляем небольшой пул из основной БД: так новые/обогащённые компании,
    # которых не было в статическом индексе 2000 поставщиков, тоже получают шанс
    # попасть в итоговый TOP-5 после комплексного re-ranking.
    db_limit = 120 if len(candidates) < 20 else 45
    preliminary_ids = _prefilter_supplier_ids(procurement, limit=db_limit)
    existing_ids = {s.id for s in candidates}
    supplement_ids = [sid for sid in preliminary_ids if sid not in existing_ids]
    if len(candidates) < 20:
        used_fallback = True
        candidates = []
        supplement_ids = preliminary_ids
    loaded = Supplier.query.options(selectinload(Supplier.contracts)).filter(Supplier.id.in_(supplement_ids)).all() if supplement_ids else []
    by_id = {s.id: s for s in loaded}
    candidates.extend(by_id[sid] for sid in supplement_ids if sid in by_id)

    # 2) Второй этап — основной backend: E5/OKPD2/опыт/win-rate/
    # география/отзывы/нагрузка. Именно этот этап формирует итоговый TOP-5.
    warm_similarity_cache(procurement, candidates)
    items = [_build_card(procurement, s, retrieval_by_inn.get(s.inn)) for s in candidates]
    filtered = [x for x in items if not requested_types or x["company_type"] in requested_types]

    # Ролевой фильтр применяется уже после определения типа компании.
    # Если модельные кандидаты не дали 5 результатов нужного типа, расширяем
    # пул из всей локальной БД, а не показываем искусственно пустую выдачу.
    if requested_types and len(filtered) < TOP_LIMIT:
        used_fallback = True
        existing_ids = {s.id for s in candidates}
        supplement_ids = [sid for sid in _prefilter_supplier_ids(procurement, limit=220) if sid not in existing_ids]
        supplement_loaded = Supplier.query.options(selectinload(Supplier.contracts)).filter(Supplier.id.in_(supplement_ids)).all() if supplement_ids else []
        by_id = {s.id: s for s in supplement_loaded}
        supplement = [by_id[sid] for sid in supplement_ids if sid in by_id]
        warm_similarity_cache(procurement, supplement)
        extra = [_build_card(procurement, s, retrieval_by_inn.get(s.inn)) for s in supplement]
        items.extend(extra)
        filtered.extend(x for x in extra if x["company_type"] in requested_types)

    filtered.sort(
        key=lambda x: (
            x["score"],
            x.get("candidate_similarity") if x.get("candidate_similarity") is not None else -1,
            x["metrics"]["semantic"],
            x["wins_count"],
        ),
        reverse=True,
    )
    top = filtered[:TOP_LIMIT]

    selected = Supplier.query.filter_by(inn=procurement.selected_supplier_inn).first() if procurement.selected_supplier_inn else None
    return jsonify({
        "items": top,
        "meta": {
            "total": len(filtered),
            "returned": len(top),
            "top_limit": TOP_LIMIT,
            "candidate_pool": len(items),
            "full_pool": Supplier.query.count(),
            "company_types": sorted(requested_types),
            "selected_supplier_inn": procurement.selected_supplier_inn,
            "selected_supplier_name": selected.name if selected else None,
            "selected_at": procurement.selected_at.isoformat() if procurement.selected_at else None,
            "retrieval": {
                "engine": retrieval.get("engine", "db-prefilter"),
                "ok": bool(retrieval.get("ok")),
                "model": retrieval.get("model"),
                "indexed_suppliers": retrieval.get("indexed_suppliers"),
                "returned_by_model": len(retrieval.get("items", [])),
                "matched_in_database": model_matched_count,
                "fallback_used": used_fallback,
                "reason": retrieval.get("reason"),
            },
        },
    })


@bp.post("/<procurement_number>/select")
@customer_required
def select_supplier(procurement_number: str):
    procurement = Procurement.query.filter_by(procurement_number=procurement_number).first_or_404()
    user = current_user()
    if procurement.customer_inn != user.organization_inn or procurement.source_system != "USER":
        return jsonify({"error": {"code": "foreign_procurement", "message": "Можно выбирать исполнителя только в своих заявках"}}), 403
    if procurement.deleted_at is not None:
        return jsonify({"error": {"code": "request_deleted", "message": "Заявка удалена"}}), 410
    if procurement.status not in {"matching", "selected"} or procurement.completed_at or procurement.archived_at:
        return jsonify({
            "error": {
                "code": "selection_locked",
                "message": "После завершения или архива заказа менять исполнителя нельзя.",
            },
            "details_url": f"/contracts/{procurement.procurement_number}",
        }), 409

    inn = str((request.get_json(silent=True) or {}).get("supplier_inn", "")).strip()
    supplier = Supplier.query.filter_by(inn=inn).first()
    if not supplier:
        return jsonify({"error": {"code": "invalid_supplier", "message": "Контрагент не найден"}}), 400

    previous_supplier_inn = procurement.selected_supplier_inn
    procurement.selected_supplier_inn = supplier.inn
    procurement.selected_at = datetime.utcnow()
    procurement.status = "selected"
    touch(procurement)
    db.session.commit()
    invalidate_workload_cache()

    return jsonify({
        "ok": True,
        "procurement_id": procurement.procurement_number,
        "selected_supplier_inn": supplier.inn,
        "selected_supplier_name": supplier.name,
        "replaced_supplier_inn": previous_supplier_inn if previous_supplier_inn and previous_supplier_inn != supplier.inn else None,
        "selected_at": procurement.selected_at.isoformat(),
        "contacts": supplier.to_details().get("contacts", {}),
        "details_url": f"/contracts/{procurement.procurement_number}",
        "message": "Исполнитель обновлён. Контакты доступны в заявке." if previous_supplier_inn and previous_supplier_inn != supplier.inn else "Исполнитель сохранён. Контакты доступны в заявке.",
    })


def _prefilter_supplier_ids(procurement: Procurement, limit: int = 220) -> list[int]:
    """Дешёвый prefilter без загрузки 44k ORM-объектов.

    Из БД читаются только пять лёгких колонок; полноценные Supplier + contracts
    загружаются уже только для десятков лучших кандидатов. Это особенно важно
    после подключения тестовых данных: новые профили вне статического FAISS
    индекса тоже участвуют в поиске без заметной задержки интерфейса.
    """
    target = re.sub(r"\D", "", procurement.okpd2_code or "")
    query_tokens = {
        t for t in re.findall(r"[а-яёa-z0-9]+", " ".join([
            procurement.title or "", procurement.subject or "", procurement.okpd2_name or "", procurement.keywords or ""
        ]).lower()) if len(t) >= 4
    }
    rows = Supplier.query.with_entities(
        Supplier.id, Supplier.name, Supplier.specialization, Supplier.okpd2_codes, Supplier.wins_count
    ).all()

    def cheap_score(row):
        sid, name, specialization, raw_codes, wins = row
        raw_codes = raw_codes or ""
        codes = [re.sub(r"\D", "", c) for c in raw_codes.split(",") if c.strip()]
        okpd = 0
        if target and target in codes:
            okpd = 1000
        elif len(target) >= 4 and any(c[:4] == target[:4] for c in codes if len(c) >= 4):
            okpd = 650
        elif len(target) >= 2 and any(c[:2] == target[:2] for c in codes if len(c) >= 2):
            okpd = 300
        profile = " ".join([name or "", specialization or "", raw_codes]).lower()
        overlap = sum(1 for token in query_tokens if token in profile)
        history = min(int(wins or 0), 50)
        return okpd + overlap * 45 + history, int(wins or 0), int(sid)

    ranked = sorted(rows, key=cheap_score, reverse=True)
    take = max(30, min(limit, len(ranked)))
    return [int(row[0]) for row in ranked[:take]]


def _prefilter_suppliers(procurement: Procurement, suppliers: list[Supplier], limit: int = 220) -> list[Supplier]:
    target = re.sub(r"\D", "", procurement.okpd2_code or "")
    query_tokens = {
        t for t in re.findall(r"[а-яёa-z0-9]+", " ".join([
            procurement.title or "", procurement.subject or "", procurement.okpd2_name or "", procurement.keywords or ""
        ]).lower()) if len(t) >= 4
    }

    def cheap_score(supplier: Supplier):
        raw_codes = supplier.okpd2_codes or ""
        codes = [re.sub(r"\D", "", c) for c in raw_codes.split(",") if c.strip()]
        okpd = 0
        if target and target in codes:
            okpd = 1000
        elif len(target) >= 4 and any(c[:4] == target[:4] for c in codes if len(c) >= 4):
            okpd = 650
        elif len(target) >= 2 and any(c[:2] == target[:2] for c in codes if len(c) >= 2):
            okpd = 300
        profile = " ".join([supplier.name or "", supplier.specialization or "", raw_codes]).lower()
        overlap = sum(1 for token in query_tokens if token in profile)
        history = min(int(supplier.wins_count or 0), 50)
        return okpd + overlap * 45 + history

    ranked = sorted(suppliers, key=lambda s: (cheap_score(s), int(s.wins_count or 0)), reverse=True)
    return ranked[: max(30, min(limit, len(ranked)))]


def _contracts_summary(supplier: Supplier) -> dict:
    """Объём выигранных контрактов для колонки «Объём контрактов» в списке."""
    won = [c for c in (supplier.contracts or []) if c.is_winner]
    total = sum(float(c.amount or 0) for c in won)
    return {
        "contracts_count": len(won) if won else int(supplier.wins_count or 0),
        "contracts_sum_mln": round(total / 1_000_000, 1),
    }


def _build_card(procurement: Procurement, supplier: Supplier, retrieval: dict | None = None) -> dict:
    scores = compute_score(procurement, supplier)
    role = classify_role(supplier, procurement)
    reviews = review_summary(supplier.id)
    load = workload_summary(supplier.inn)
    geo = logistics_score(procurement, supplier)
    participations = int(supplier.participation_count or 0)
    wins = int(supplier.wins_count or 0)
    win_rate = round(wins / participations * 100, 1) if participations else None

    return {
        **supplier.to_card(),
        "company_type": role,
        "coords": {"lat": supplier.lat, "lon": supplier.lon},
        "score": scores["total"],
        "relevance_label": relevance_label(scores["total"]),
        "tags": build_tags(procurement, supplier, scores),
        "wins_count": wins,
        "participation_count": participations,
        **_contracts_summary(supplier),
        "metrics": {
            "semantic": scores["product"],
            "experience": scores["experience"],
            "win_rate": win_rate,
            "geography": scores["geography"],
            "distance_km": geo["distance_km"],
            "rating": reviews["avg"],
            "reviews_count": reviews["count"],
            "workload": load["label"],
            "workload_level": load["level"],
        },
        "logistics_note": geo["note"],
        "workload_warning": load["warning"],
        # Технический сигнал первого этапа. Не показываем его пользователю как
        # «вероятность»: это cosine-like similarity из FAISS, используемая для
        # формирования пула и tie-break в итоговом ranking.
        "candidate_similarity": round(float(retrieval["similarity"]), 4) if retrieval else None,
        "candidate_rank": int(retrieval["rank"]) if retrieval else None,
        "candidate_engine": "all-minilm+faiss" if retrieval else "db-prefilter",
    }
