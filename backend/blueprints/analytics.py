"""API аналитики."""
from flask import Blueprint, jsonify

from backend.services import analytics as svc

bp = Blueprint("analytics", __name__)


@bp.get("/regions")
def regions():
    return _handle(svc.by_region)


@bp.get("/company-types")
def company_types():
    return _handle(svc.by_company_type)


@bp.get("/revenue-buckets")
def revenue_buckets():
    return _handle(svc.by_revenue_bucket)


@bp.get("/top-contracts")
def top_contracts():
    return _handle(lambda: svc.top_by_contracts(limit=10))


def _handle(func):
    """Универсальный враппер: NotImplemented → 501, ошибки → 500."""
    try:
        return jsonify(func())
    except NotImplementedError as exc:
        return jsonify({
            "error": {"code": "not_implemented", "message": str(exc)}
        }), 501
    except Exception as exc:  # noqa: BLE001
        return jsonify({
            "error": {"code": "internal_error", "message": str(exc)}
        }), 500
