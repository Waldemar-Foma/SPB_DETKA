"""API аналитики."""
from flask import Blueprint, jsonify
from backend.services import analytics as svc

bp = Blueprint("analytics", __name__)

@bp.get("/regions")
def regions(): return jsonify(svc.by_region())

@bp.get("/company-types")
def company_types(): return jsonify(svc.by_company_type())

@bp.get("/revenue-buckets")
def revenue_buckets(): return jsonify(svc.by_revenue_bucket())

@bp.get("/top-contracts")
def top_contracts(): return jsonify(svc.top_by_contracts(limit=10))
