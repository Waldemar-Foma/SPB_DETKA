from __future__ import annotations

import html
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import quote_plus

import requests

from backend.extensions import db
from backend.services.geography import approx_supplier_coords

DADATA_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party"
FNS_SEARCH_URL = "https://egrul.nalog.ru/"
FNS_RESULT_URL = "https://egrul.nalog.ru/search-result/{token}"
LOGGER = logging.getLogger(__name__)
PLACEHOLDER_PREFIX = "Контрагент ИНН"
LEGAL_PREFIX = r"(?:ООО|АО|ПАО|ОАО|ЗАО|НАО|ИП|ФГУП|ГУП|МУП|АНО|ФГБУ|ГБУ|МБУ|ФКУ|ГКУ)"


def _is_placeholder(name: str | None) -> bool:
    value = (name or "").strip()
    return not value or value.startswith(PLACEHOLDER_PREFIX)


def _clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _dadata(inn: str) -> dict | None:
    token = (os.getenv("DADATA_TOKEN") or "").strip()
    if not token:
        return None
    try:
        r = requests.post(
            DADATA_URL,
            headers={"Authorization": f"Token {token}", "Content-Type": "application/json", "Accept": "application/json"},
            json={"query": inn},
            timeout=3.5,
        )
        if not r.ok:
            return None
        suggestions = (r.json() or {}).get("suggestions") or []
        if not suggestions:
            return None
        data = suggestions[0].get("data") or {}
        name = data.get("name") or {}
        address = data.get("address") or {}
        addr_data = address.get("data") or {}
        legal_name = (name.get("short_with_opf") or suggestions[0].get("value") or "").strip()
        if not legal_name:
            return None
        return {
            "name": legal_name,
            "ogrn": str(data.get("ogrn") or "")[:15],
            "primary_okved": str(data.get("okved") or "")[:32],
            "region": str(addr_data.get("region_with_type") or "")[:128],
            "address": str(address.get("value") or "")[:1000],
            "source": "dadata",
        }
    except (requests.RequestException, ValueError):
        return None


def _fns(inn: str) -> dict | None:
    """Resolve a company/IP by INN through the official FNS EGRUL/EGRIP service.

    The public service uses a two-step request: submit the query and receive a
    temporary token, then fetch the matching rows. No API key is required.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://egrul.nalog.ru/index.html",
        "X-Requested-With": "XMLHttpRequest",
    })
    try:
        first = session.post(
            FNS_SEARCH_URL,
            data={
                "vyp3CaptchaToken": "",
                "page": "",
                "query": inn,
                "region": "",
                "PreventChromeAutocomplete": "",
            },
            timeout=7.0,
        )
        if not first.ok:
            LOGGER.warning("FNS lookup submit failed for INN %s: HTTP %s", inn, first.status_code)
            return None
        payload = first.json() or {}
        token = str(payload.get("t") or payload.get("token") or "").strip()
        if not token:
            LOGGER.warning("FNS lookup returned no token for INN %s: %s", inn, payload)
            return None

        # The result is usually ready immediately, but occasionally FNS needs a
        # short moment. Retry twice without making the TOP-5 noticeably slower.
        rows = []
        for attempt in range(3):
            result = session.get(FNS_RESULT_URL.format(token=token), params={"r": token, "_": int(time.time() * 1000)}, timeout=7.0)
            if result.ok:
                body = result.json() or {}
                rows = body.get("rows") or body.get("items") or []
                if rows:
                    break
            if attempt < 2:
                time.sleep(0.25)

        normalized_inn = re.sub(r"\D", "", inn)
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_inn = re.sub(r"\D", "", str(row.get("i") or row.get("inn") or row.get("ИНН") or ""))
            if row_inn != normalized_inn:
                continue
            name = _clean_text(str(row.get("n") or row.get("name") or row.get("НаимЮЛ") or row.get("ФИОП") or ""))
            if not name:
                continue
            address = _clean_text(str(row.get("a") or row.get("address") or ""))
            ogrn = re.sub(r"\D", "", str(row.get("o") or row.get("ogrn") or ""))[:15]
            return {
                "name": name[:255],
                "ogrn": ogrn,
                "address": address[:1000],
                "source": "fns_egrul",
            }
        LOGGER.info("FNS lookup returned no exact row for INN %s", inn)
    except (requests.RequestException, ValueError, TypeError) as exc:
        LOGGER.warning("FNS lookup failed for INN %s: %s", inn, exc)
    return None


def _extract_legal_name(text: str, inn: str) -> str | None:
    clean = _clean_text(text)
    if inn not in re.sub(r"\D", "", clean):
        return None

    # Typical public-registry snippets: ООО «Ромашка», ИНН 123... / ООО РОМАШКА - ...
    patterns = [
        rf"\b({LEGAL_PREFIX}\s*[«\"']?[^,;|—–\n]{{2,120}}?[»\"']?)\s*(?:,|\||—|–|-)?\s*(?:ИНН)?\s*{re.escape(inn)}\b",
        rf"\b({LEGAL_PREFIX}\s*[«\"']?[^,;|—–\n]{{2,100}}?[»\"']?)\s*(?:,|\||—|–|-)\s*ИНН\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, clean, flags=re.I)
        if m:
            name = re.sub(r"\s+", " ", m.group(1)).strip(" ,;|-—–")
            if 4 <= len(name) <= 180:
                return name
    return None


def _public_search(inn: str) -> dict | None:
    """Best-effort parser for a legal name from public search results.

    No guessed company name is written: a candidate is accepted only when the
    same snippet/title also contains the requested INN.
    """
    url = "https://html.duckduckgo.com/html/?q=" + quote_plus(f'ИНН {inn} организация')
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4.0)
        if not r.ok:
            return None
        blocks = re.findall(
            r'<a[^>]+class="[^"]*result__a[^"]*"[^>]*>(.*?)</a>|<(?:a|div)[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</(?:a|div)>',
            r.text,
            flags=re.I | re.S,
        )
        texts = []
        for a, b in blocks:
            text = _clean_text(a or b)
            if text:
                texts.append(text)
        # Also inspect the entire result page text as a fallback, but still
        # require the exact INN next to a legal-form company name.
        texts.append(_clean_text(r.text))
        for text in texts:
            name = _extract_legal_name(text, inn)
            if name:
                return {"name": name, "source": "public_web"}
    except requests.RequestException:
        return None
    return None


def _lookup(inn: str) -> tuple[str, dict | None]:
    return inn, (_dadata(inn) or _fns(inn) or _public_search(inn))


def enrich_top_supplier_identities(suppliers: list) -> dict[str, dict]:
    """Enrich missing company names for the final TOP-5 and persist them.

    Network requests run concurrently so five lookups do not stack their
    timeout. Companies which already have a real name are not queried again.
    """
    targets = [s for s in suppliers if _is_placeholder(getattr(s, "name", None))]
    results: dict[str, dict] = {}

    if targets:
        with ThreadPoolExecutor(max_workers=min(5, len(targets))) as pool:
            futures = {pool.submit(_lookup, str(s.inn)): s for s in targets}
            for future in as_completed(futures):
                supplier = futures[future]
                try:
                    inn, payload = future.result()
                except Exception as exc:
                    inn, payload = str(supplier.inn), None
                    LOGGER.warning("Identity lookup crashed for INN %s: %s", inn, exc)
                if payload and payload.get("name"):
                    results[inn] = payload

    now = datetime.utcnow()
    changed = False
    by_inn = {str(s.inn): s for s in suppliers}
    for inn, payload in results.items():
        supplier = by_inn.get(inn)
        if not supplier:
            continue
        if _is_placeholder(supplier.name):
            supplier.name = str(payload["name"])[:255]
            changed = True
        for field in ("ogrn", "primary_okved", "address"):
            value = payload.get(field)
            if value and not getattr(supplier, field, None):
                setattr(supplier, field, value)
                changed = True
        if payload.get("region") and (not supplier.region or supplier.region == "Россия"):
            supplier.region = str(payload["region"])[:128]
            changed = True
        supplier.enrichment_updated_at = now
        source = supplier.data_source or ""
        marker = "+identity"
        if marker not in source:
            supplier.data_source = (source + marker)[:64]
        if supplier.lat is None or supplier.lon is None:
            supplier.lat, supplier.lon = approx_supplier_coords(inn, supplier.region or "Россия")
            changed = True

    # Coordinates are required by the map even when the public-name lookup
    # returned nothing. Fill them for all final TOP-5 suppliers.
    for supplier in suppliers:
        if supplier.lat is None or supplier.lon is None:
            supplier.lat, supplier.lon = approx_supplier_coords(str(supplier.inn), supplier.region or "Россия")
            changed = True

    if changed:
        db.session.commit()
    return results
