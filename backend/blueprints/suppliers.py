from flask import Blueprint, jsonify

from backend.models import Procurement, Supplier
from backend.services.matching_engine import compute_score

bp = Blueprint("suppliers", __name__)


@bp.get("/<inn>/details")
def details(inn: str):
    """Возвращает расширенный профиль контрагента."""
    supplier = Supplier.query.filter_by(inn=inn).first_or_404()
    procurement = Procurement.query.first()

    scores = compute_score(procurement, supplier) if procurement else _empty_scores()
    contracts = supplier.contracts or []

    return jsonify({
        **supplier.to_details(),
        "scoring_breakdown": {
            "total": scores["total"],
            "okpd2_match": scores["okpd2"],
            "product_match": scores["product"],
            "contracts_match": scores["experience"],
            "region_match": scores["region"],
            "scale_match": scores["scale"],
        },
        "contract_history": {
            "total_contracts": len(contracts),
            "total_amount_rub": sum(float(c.amount) for c in contracts),
            "by_years": _group_by_year(contracts),
        },
    })


def _group_by_year(contracts) -> dict[str, int]:
    """Группирует контракты по годам для гистограммы."""
    result: dict[str, int] = {}
    for c in contracts:
        key = str(c.year)
        result[key] = result.get(key, 0) + 1
    return dict(sorted(result.items()))


def _empty_scores() -> dict:
    """Заглушка, если в базе нет ни одной закупки."""
    return {"total": 0, "okpd2": 0, "product": 0, "experience": 0, "region": 0, "scale": 0}