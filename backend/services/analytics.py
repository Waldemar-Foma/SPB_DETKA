from __future__ import annotations

from sqlalchemy import func

from backend.models import Supplier

LOCAL = ("Санкт-Петербург", "Ленинградская область")


def by_region() -> list[dict]:
    rows = (Supplier.query.with_entities(Supplier.region, func.count(Supplier.id))
            .filter(Supplier.region.in_(LOCAL)).group_by(Supplier.region).all())
    return [{"region": r, "count": c} for r, c in rows]


def by_company_type() -> list[dict]:
    rows = (Supplier.query.with_entities(Supplier.company_type, func.count(Supplier.id))
            .filter(Supplier.region.in_(LOCAL)).group_by(Supplier.company_type).all())
    return [{"company_type": r, "count": c} for r, c in rows]


def by_revenue_bucket() -> list[dict]:
    buckets = [(0, 50e6, "до 50 млн"), (50e6, 300e6, "50–300 млн"), (300e6, 1e9, "300 млн–1 млрд"), (1e9, float("inf"), "от 1 млрд")]
    result = []
    for lo, hi, label in buckets:
        q = Supplier.query.filter(Supplier.region.in_(LOCAL), Supplier.revenue_annual >= lo)
        if hi != float("inf"):
            q = q.filter(Supplier.revenue_annual < hi)
        result.append({"bucket": label, "count": q.count()})
    return result


def top_by_contracts(limit: int = 10) -> list[dict]:
    rows = (Supplier.query.filter(Supplier.region.in_(LOCAL))
            .order_by(Supplier.wins_count.desc(), Supplier.name.asc()).limit(limit).all())
    return [{"inn": s.inn, "name": s.name, "wins": s.wins_count, "region": s.region} for s in rows]
