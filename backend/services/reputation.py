from __future__ import annotations

import html
import re
from functools import lru_cache
from datetime import datetime, timedelta
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests

from backend.extensions import db
from backend.models import ExternalMention, Procurement, Supplier, SupplierReview

CACHE_TTL = timedelta(hours=24)
AGGREGATORS = ("yandex.", "2gis.", "google.", "zoon.", "otzovik.", "irecommend.", "rusprofile.", "checko.")


@lru_cache(maxsize=8192)
def review_summary(supplier_id: int) -> dict:
    rows = SupplierReview.query.filter_by(supplier_id=supplier_id).all()
    if not rows:
        return {"avg": None, "count": 0, "quality": None, "deadlines": None, "communication": None}

    def avg(field):
        vals = [getattr(r, field) for r in rows if getattr(r, field) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    return {
        "avg": avg("rating"),
        "count": len(rows),
        "quality": avg("quality_rating"),
        "deadlines": avg("deadlines_rating"),
        "communication": avg("communication_rating"),
    }


@lru_cache(maxsize=8192)
def workload_summary(supplier_inn: str) -> dict:
    active = Procurement.query.filter(
        Procurement.selected_supplier_inn == supplier_inn,
        Procurement.source_system == "USER",
        Procurement.deleted_at.is_(None),
        Procurement.archived_at.is_(None),
        Procurement.status.in_(["selected", "matching"]),
    ).count()
    if active >= 5:
        return {"active_requests": active, "level": "high", "label": "Высокая нагрузка", "warning": f"Компания уже выбрана в {active} активных заявках сервиса. Возможна повышенная загрузка — уточните сроки до оформления заказа."}
    if active >= 2:
        return {"active_requests": active, "level": "medium", "label": "Есть текущая нагрузка", "warning": f"Компания уже выбрана в {active} активных заявках сервиса. Рекомендуем подтвердить доступные сроки."}
    if active == 1:
        return {"active_requests": 1, "level": "low", "label": "Нагрузка не выглядит высокой", "warning": None}
    return {"active_requests": 0, "level": "unknown", "label": "Нет данных о текущей загрузке", "warning": None}


def _web_search(query: str, limit: int = 6) -> list[dict]:
    """Small public web search helper. Returns only actually received results."""
    url = "https://html.duckduckgo.com/html/?q=" + quote_plus(query)
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        response.raise_for_status()
    except Exception:
        return []

    text = response.text
    links = re.findall(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', text, flags=re.I | re.S)
    snippets = re.findall(r'<(?:a|div)[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</(?:a|div)>', text, flags=re.I | re.S)
    rows = []
    for idx, (href, title_html) in enumerate(links[:limit]):
        clean_url = _unwrap_ddg(html.unescape(href))
        if not clean_url.startswith("http"):
            continue
        rows.append({
            "url": clean_url,
            "title": _strip_html(title_html)[:500],
            "snippet": _strip_html(snippets[idx] if idx < len(snippets) else "")[:1600],
            "source": urlparse(clean_url).netloc.lower().removeprefix("www.") or "web",
        })
    return rows


def search_external_mentions(supplier: Supplier, force: bool = False, limit: int = 4) -> list[ExternalMention]:
    cutoff = datetime.utcnow() - CACHE_TTL
    cached = ExternalMention.query.filter_by(supplier_id=supplier.id).filter(ExternalMention.found_at >= cutoff).order_by(ExternalMention.found_at.desc()).limit(limit).all()
    if cached and not force:
        return cached

    # This is deliberately a review/reputation search, not a generated rating.
    rows = _web_search(f'"{supplier.name}" {supplier.inn} отзывы', limit=limit)
    if not rows:
        return cached

    created = []
    for item in rows:
        row = ExternalMention.query.filter_by(supplier_id=supplier.id, url=item["url"]).first()
        if not row:
            row = ExternalMention(
                supplier_id=supplier.id, source=item["source"], title=item["title"],
                url=item["url"], snippet=item["snippet"],
            )
            db.session.add(row)
        else:
            row.title, row.snippet, row.source, row.found_at = item["title"], item["snippet"], item["source"], datetime.utcnow()
        created.append(row)
    if created:
        db.session.commit()
    return ExternalMention.query.filter_by(supplier_id=supplier.id).order_by(ExternalMention.found_at.desc()).limit(limit).all()


def enrich_contacts_from_web(supplier: Supplier) -> bool:
    """Try to enrich contacts from actual public search results.

    Raw hackathon CSV files do not contain phone/e-mail/site. We therefore
    search the public web *after the customer selects a company*. Nothing is
    synthesized: if a phone/e-mail cannot be observed in a real snippet, the
    corresponding field remains empty.
    """
    last_try = getattr(supplier, "contact_lookup_at", None)
    if last_try and datetime.utcnow() - last_try < CACHE_TTL:
        return False
    if supplier.phone and supplier.email and supplier.website:
        supplier.contact_lookup_at = datetime.utcnow()
        db.session.commit()
        return False
    rows = _web_search(
        f'"{supplier.name}" {supplier.inn} контакты телефон email официальный сайт',
        limit=8,
    )
    # Cached reputation snippets can occasionally contain the same contacts;
    # use them only as a factual fallback if the contacts query is unavailable.
    if not rows:
        rows = [{"url": m.url, "title": m.title or "", "snippet": m.snippet or "", "source": m.source}
                for m in search_external_mentions(supplier, limit=6)]

    blob = " ".join((r.get("title", "") + " " + r.get("snippet", "")) for r in rows)
    changed = False
    if not supplier.email:
        match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", blob, flags=re.I)
        if match:
            supplier.email = match.group(0)[:128]
            changed = True
    if not supplier.phone:
        match = re.search(r"(?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s-]*\d{2}[\s-]*\d{2}", blob)
        if match:
            supplier.phone = re.sub(r"\s+", " ", match.group(0))[:64]
            changed = True
    if not supplier.website:
        for item in rows:
            host = urlparse(item.get("url") or "").netloc.lower().removeprefix("www.")
            if host and not any(a in host for a in AGGREGATORS):
                supplier.website = f"https://{host}"
                changed = True
                break
    supplier.contact_lookup_at = datetime.utcnow()
    if changed:
        source = supplier.data_source or ""
        if "+web" not in source:
            supplier.data_source = source + "+web"
    db.session.commit()
    return changed


def invalidate_review_cache() -> None:
    review_summary.cache_clear()


def invalidate_workload_cache() -> None:
    workload_summary.cache_clear()


def _strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _unwrap_ddg(url: str) -> str:
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target) if target else url
    if url.startswith("//duckduckgo.com/l/"):
        parsed = urlparse("https:" + url)
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target) if target else "https:" + url
    return url
