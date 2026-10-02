from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from backend.models import ExternalMention, Procurement, RegistrySync, Supplier, SupplierReview
from backend.services.auth import current_user
from backend.services.explanation import explain
from backend.services.geography import logistics_score
from backend.services.matching_engine import compute_score
from backend.services.reputation import review_summary, search_external_mentions, workload_summary
from backend.services.role_classifier import classify_role, role_reason

bp = Blueprint("suppliers", __name__)


def registry_role(supplier: Supplier) -> str:
    if supplier.is_gisp_manufacturer:
        return "Производитель"
    if (supplier.primary_okved or "").startswith("46"):
        return "Дистрибьютор / Оптовик"
    return "Поставщик"


@bp.get("/")
def registry_list():
    q = (request.args.get("q") or "").strip()
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(max(request.args.get("per_page", 50, type=int), 1), 200)
    query = Supplier.query
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Supplier.name.ilike(like), Supplier.inn.ilike(like), Supplier.specialization.ilike(like)))
    pagination = query.order_by(Supplier.wins_count.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "items": [{**s.to_card(), "company_type": registry_role(s)} for s in pagination.items],
        "meta": {"page": page, "per_page": per_page, "total": pagination.total, "pages": pagination.pages},
    })


@bp.get("/registry-status")
def registry_status():
    latest = RegistrySync.query.order_by(RegistrySync.finished_at.desc()).first()
    return jsonify({
        "latest": _sync_to_dict(latest),
        "gisp_manufacturers": Supplier.query.filter(Supplier.is_gisp_manufacturer.is_(True)).count(),
        "enriched_suppliers": Supplier.query.filter(Supplier.enrichment_updated_at.isnot(None)).count(),
    })


@bp.get("/<inn>/details")
def details(inn: str):
    supplier = Supplier.query.filter_by(inn=inn).first_or_404()
    procurement_number = request.args.get("procurement_id")
    procurement = Procurement.query.filter_by(procurement_number=procurement_number).first() if procurement_number else None
    user = current_user()
    if procurement and user and user.account_role != "admin" and procurement.customer_inn != user.organization_inn:
        return jsonify({"error": {"code": "forbidden", "message": "Нет доступа к этой заявке"}}), 403

    scores = compute_score(procurement, supplier) if procurement else _empty_scores()
    role = classify_role(supplier, procurement) if procurement else registry_role(supplier)
    reviews = review_summary(supplier.id)
    workload = workload_summary(supplier.inn)
    geo = logistics_score(procurement, supplier) if procurement else None
    participations = int(supplier.participation_count or 0)
    wins = int(supplier.wins_count or 0)
    win_rate = round(wins / participations * 100, 1) if participations else None

    can_see_contacts = bool(procurement and procurement.selected_supplier_inn == supplier.inn and user and (user.account_role == "admin" or procurement.customer_inn == user.organization_inn))
    contacts = supplier.to_details()["contacts"] if can_see_contacts else None
    internal_reviews = SupplierReview.query.filter_by(supplier_id=supplier.id).order_by(SupplierReview.created_at.desc()).limit(10).all()
    cached_mentions = ExternalMention.query.filter_by(supplier_id=supplier.id).order_by(ExternalMention.found_at.desc()).limit(4).all()

    return jsonify({
        **supplier.to_details(),
        "contacts": contacts,
        "contacts_locked": not can_see_contacts,
        "company_type": role,
        "role_reason": role_reason(supplier, procurement) if procurement else "Классификация рассчитана по реестровым признакам.",
        "ai_explanation": {"status": "pending", "text": None, "source": None} if procurement else None,
        "scoring_breakdown": {
            "total": scores["total"],
            "semantic": scores.get("product", 0),
            "category_experience": scores.get("experience", 0),
            "win_rate_score": scores.get("win_rate", 0),
            "customer_history": scores.get("customer", 0),
            "geography": scores.get("geography", 0),
            "reviews": scores.get("reviews", 0),
            "workload": scores.get("workload", 0),
        },
        "metrics": {
            "win_rate": win_rate,
            "wins": wins,
            "participations": participations,
            "rating": reviews["avg"],
            "reviews_count": reviews["count"],
            "workload": workload,
            "logistics": geo,
        },
        "reviews": [{
            "rating": r.rating,
            "quality": r.quality_rating,
            "deadlines": r.deadlines_rating,
            "communication": r.communication_rating,
            "comment": r.comment,
            "created_at": r.created_at.isoformat(),
        } for r in internal_reviews],
        "external_mentions": [_mention(m) for m in cached_mentions],
    })


@bp.get("/<inn>/explanation")
def explanation_for(inn: str):
    supplier = Supplier.query.options(selectinload(Supplier.contracts), selectinload(Supplier.reviews)).filter_by(inn=inn).first_or_404()
    procurement_number = request.args.get("procurement_id")
    if not procurement_number:
        return jsonify({"error": {"code": "missing_procurement", "message": "Не указана заявка"}}), 400
    procurement = Procurement.query.filter_by(procurement_number=procurement_number).first_or_404()
    user = current_user()
    if user and user.account_role != "admin" and procurement.customer_inn != user.organization_inn:
        return jsonify({"error": {"code": "forbidden", "message": "Нет доступа к этой заявке"}}), 403

    scores = compute_score(procurement, supplier)
    role = classify_role(supplier, procurement)
    result = explain(procurement, supplier, scores, role)
    return jsonify({**result, "status": "ready"})


@bp.post("/<inn>/external-reputation")
def external_reputation(inn: str):
    supplier = Supplier.query.filter_by(inn=inn).first_or_404()
    mentions = search_external_mentions(supplier, force=True, limit=4)
    return jsonify({"items": [_mention(m) for m in mentions]})


def _mention(m):
    return {"source": m.source, "title": m.title, "url": m.url, "snippet": m.snippet, "found_at": m.found_at.isoformat()}


def _sync_to_dict(sync):
    if not sync:
        return None
    return {"source": sync.source, "status": sync.status, "rows_total": sync.rows_total, "matched_suppliers": sync.matched_suppliers, "message": sync.message, "finished_at": sync.finished_at.isoformat() if sync.finished_at else None}


def _empty_scores():
    return {"total": 0, "product": 0, "okpd2": 0, "experience": 0, "win_rate": 0, "customer": 0, "geography": 0, "reviews": 0, "workload": 0, "weights": {}}
