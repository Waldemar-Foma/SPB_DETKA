from __future__ import annotations

from datetime import datetime, timedelta

from backend.extensions import db
from backend.models import Procurement
from backend.services.reputation import invalidate_workload_cache

ARCHIVE_AFTER_DAYS = 365


def archive_stale_requests(customer_inn: str | None = None) -> int:
    """Архивирует пользовательские заявки, которые не менялись год.

    Импортированные исторические закупки этим механизмом не затрагиваются.
    """
    cutoff = datetime.utcnow() - timedelta(days=ARCHIVE_AFTER_DAYS)
    q = Procurement.query.filter(
        Procurement.source_system == "USER",
        Procurement.deleted_at.is_(None),
        Procurement.archived_at.is_(None),
        Procurement.updated_at < cutoff,
    )
    if customer_inn:
        q = q.filter(Procurement.customer_inn == customer_inn)
    rows = q.all()
    for row in rows:
        row.status = "archived"
        row.archived_at = datetime.utcnow()
    if rows:
        db.session.commit()
        invalidate_workload_cache()
    return len(rows)


def touch(procurement: Procurement) -> None:
    procurement.updated_at = datetime.utcnow()
