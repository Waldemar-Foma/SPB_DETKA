from __future__ import annotations

from flask import Blueprint, jsonify, request

from backend.models import Procurement, Supplier
from backend.services.matching_engine import build_tags, compute_score, relevance_label
from backend.services.search_service import (
    DEFAULT_LIMIT,
    filter_and_sort,
    paginate,
)

bp = Blueprint("procurement", __name__)

SUPPORTED_FILTERS = ("company_type", "region", "min_experience", "min_revenue", "q")


@bp.post("/analyze")
def analyze():
    """Распознаёт закупку по текстовому запросу."""
    query = (request.get_json(silent=True) or {}).get("query", "").strip()
    procurement = _find_procurement(query)

    if not procurement:
        return jsonify({
            "error": {"code": "not_found", "message": "Закупка не найдена"}
        }), 404

    return jsonify({
        **procurement.to_dict(),
        "total_found": Supplier.query.count(),
    })


@bp.get("/<procurement_number>/suppliers")
def suppliers_for(procurement_number: str):
    """Возвращает ранжированный список контрагентов для закупки.

    Query-параметры:
      sort          — ключ сортировки (по умолчанию relevance_desc)
      limit, offset — пагинация
      company_type, region, min_experience, min_revenue, q — фильтры
    """
    procurement = Procurement.query.filter_by(
        procurement_number=procurement_number
    ).first_or_404()

    items = [_build_card(procurement, s) for s in Supplier.query.all()]
    filters = {key: request.args.get(key) for key in SUPPORTED_FILTERS}
    sort_key = request.args.get("sort", "relevance_desc")

    ranked = filter_and_sort(items, filters, sort_key)

    limit = request.args.get("limit", DEFAULT_LIMIT, type=int)
    offset = request.args.get("offset", 0, type=int)

    return jsonify(paginate(ranked, limit=limit, offset=offset))


def _find_procurement(query: str) -> Procurement | None:
    """Ищет закупку по названию, номеру или ключевым словам."""
    if not query:
        return Procurement.query.first()

    by_number = Procurement.query.filter_by(procurement_number=query.strip()).first()
    if by_number:
        return by_number

    by_title = Procurement.query.filter(
        Procurement.title.ilike(f"%{query}%")
    ).first()
    if by_title:
        return by_title

    lowered = query.lower()
    for procurement in Procurement.query.all():
        keywords = (procurement.keywords or "").lower()
        if any(kw.strip() and kw.strip() in lowered for kw in keywords.split(",")):
            return procurement

    return Procurement.query.first()


def _build_card(procurement: Procurement, supplier: Supplier) -> dict:
    """Собирает карточку контрагента с оценками, метриками и координатами."""
    scores = compute_score(procurement, supplier)
    contracts = supplier.contracts or []
    total_amount = sum(float(c.amount) for c in contracts)

    return {
        **supplier.to_card(),
        "coords": {"lat": supplier.lat, "lon": supplier.lon},
        "score": scores["total"],
        "relevance_label": relevance_label(scores["total"]),
        "tags": build_tags(procurement, supplier, scores),
        "contracts_count": len(contracts),
        "contracts_sum_mln": round(total_amount / 1e6, 1),
        "revenue_mrd": round(float(supplier.revenue_annual or 0) / 1e9, 2),
    }
