"""Обогащение локальной базы тестовыми CSV + DaData.

Задачи:
1. Скачать публичный набор из Yandex Disk (если сеть доступна) и сохранить CSV в data/test_enrichment.
2. Связать тестовые извещения/ТРУ с победителями из исходного набора Поставщики_24-25.
3. Реально обновить основную таблицу Supplier и SupplierContract, а не отдельную demo-БД.
4. При наличии DADATA_TOKEN дополнить профиль компании названием, ОГРН, ОКВЭД,
   статусом/адресом/регионом. Ответы DaData кэшируются, чтобы не тратить лимит повторно.

Секрет DaData намеренно НЕ хранится в репозитории. Передайте DADATA_TOKEN через .env / Docker.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import Supplier, SupplierContract  # noqa: E402
from scripts.build_real_db import DataArchive  # noqa: E402

DEFAULT_YANDEX_URL = (
    "https://disk.yandex.ru/d/CI8l7NXJ_k7HYA/"
    "%D0%A2%D0%B5%D1%81%D1%82%D0%BE%D0%B2%D1%8B%D0%B5%20%D0%B4%D0%B0%D0%BD%D0%BD%D1%8B%D0%B5_1140"
)
YANDEX_API = "https://cloud-api.yandex.net/v1/disk/public/resources"
DADATA_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party"
DATA_DIR = ROOT / "data" / "test_enrichment"
DADATA_CACHE = ROOT / "data" / "dadata_cache.json"
STATUS_FILE = ROOT / "instance" / "company_enrichment_status.json"
CACHE_TTL_DAYS = int(os.getenv("DADATA_CACHE_DAYS", "30"))
DADATA_WORKERS = max(1, min(8, int(os.getenv("DADATA_WORKERS", "4"))))
DADATA_TIMEOUT = float(os.getenv("DADATA_TIMEOUT", "12"))
DADATA_MAX_COMPANIES = max(0, int(os.getenv("DADATA_MAX_COMPANIES", "9900")))


def _log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def _write_status(status: str, message: str, **extra) -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "message": message,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        **extra,
    }
    if STATUS_FILE.exists():
        try:
            old = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
            if old.get("started_at") and "started_at" not in payload:
                payload["started_at"] = old["started_at"]
        except (OSError, ValueError):
            pass
    STATUS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _split_public_url(url: str) -> tuple[str, str | None]:
    """Возвращает базовую публичную ссылку и относительный путь внутри неё."""
    parsed = urlparse(url)
    parts = [x for x in parsed.path.split("/") if x]
    if len(parts) >= 2 and parts[0] == "d":
        base = f"{parsed.scheme or 'https'}://{parsed.netloc}/d/{parts[1]}"
        subpath = "/".join(unquote(x) for x in parts[2:]) or None
        return base, subpath
    return url, None


def _yandex_get_metadata(public_url: str) -> tuple[dict, str, str | None]:
    """Пробуем как полный public_key, затем base public_key + path."""
    attempts: list[tuple[str, str | None]] = [(public_url, None)]
    base, subpath = _split_public_url(public_url)
    if base != public_url or subpath:
        attempts.append((base, subpath))
    last_error = ""
    for public_key, path in attempts:
        params = {"public_key": public_key, "limit": 1000}
        if path:
            params["path"] = path
        try:
            response = requests.get(YANDEX_API, params=params, timeout=20)
            if response.ok:
                return response.json(), public_key, path
            last_error = f"HTTP {response.status_code}: {response.text[:300]}"
        except (requests.RequestException, ValueError) as exc:
            last_error = str(exc)
    raise RuntimeError(f"Yandex Disk API недоступен: {last_error or 'неизвестная ошибка'}")


def _download_href(public_key: str, path: str | None = None) -> str:
    path_variants = [path]
    if path:
        clean = str(path).replace("disk:/", "", 1).lstrip("/")
        if clean != path:
            path_variants.append(clean)
    last_error = ""
    for candidate in path_variants:
        params = {"public_key": public_key}
        if candidate:
            params["path"] = candidate
        try:
            response = requests.get(YANDEX_API + "/download", params=params, timeout=20)
            if not response.ok:
                last_error = f"HTTP {response.status_code}"
                continue
            href = response.json().get("href")
            if href:
                return str(href)
        except (requests.RequestException, ValueError) as exc:
            last_error = str(exc)
    raise RuntimeError(f"Yandex Disk не вернул ссылку download: {last_error}")


def _safe_name(name: str) -> str:
    name = Path(name or "file.csv").name.replace("\x00", "")
    return name[:240] or "file.csv"


def _download_file(public_key: str, item_path: str | None, name: str, target_dir: Path, direct_href: str | None = None) -> Path:
    href = direct_href or _download_href(public_key, item_path)
    response = requests.get(href, timeout=90, stream=True)
    response.raise_for_status()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / _safe_name(name)
    tmp = target.with_suffix(target.suffix + ".part")
    with tmp.open("wb") as fh:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                fh.write(chunk)
    os.replace(tmp, target)
    return target


def download_yandex_dataset(public_url: str, target_dir: Path = DATA_DIR) -> list[Path]:
    """Скачивает CSV из указанного публичного ресурса. При сетевой ошибке caller может использовать кэш."""
    metadata, public_key, selected_path = _yandex_get_metadata(public_url)
    kind = metadata.get("type")
    downloaded: list[Path] = []
    if kind == "file":
        name = metadata.get("name") or "dataset.csv"
        path = metadata.get("path") or selected_path
        if str(name).lower().endswith((".csv", ".zip", ".xlsx")):
            downloaded.append(_download_file(public_key, path, name, target_dir))
        return downloaded

    items = ((metadata.get("_embedded") or {}).get("items") or [])
    # Если это папка с вложенной папкой, обходим один уровень рекурсивно через API.
    queue = list(items)
    seen_paths: set[str] = set()
    while queue:
        item = queue.pop(0)
        item_path = str(item.get("path") or "")
        if item_path in seen_paths:
            continue
        seen_paths.add(item_path)
        if item.get("type") == "dir":
            try:
                params = {"public_key": public_key, "path": item_path, "limit": 1000}
                r = requests.get(YANDEX_API, params=params, timeout=20)
                if r.ok:
                    queue.extend(((r.json().get("_embedded") or {}).get("items") or []))
            except requests.RequestException:
                pass
            continue
        name = str(item.get("name") or "")
        if name.lower().endswith((".csv", ".zip", ".xlsx")):
            downloaded.append(_download_file(public_key, item_path or None, name, target_dir, str(item.get("file") or "") or None))
    return downloaded


def _cached_data_files(target_dir: Path = DATA_DIR) -> list[Path]:
    if not target_dir.exists():
        return []
    return [p for p in target_dir.iterdir() if p.is_file() and p.suffix.lower() in {".csv", ".zip", ".xlsx"}]


def _read_csv_flexible(path_or_buffer, **kwargs) -> pd.DataFrame:
    last = None
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            if hasattr(path_or_buffer, "seek"):
                path_or_buffer.seek(0)
            return pd.read_csv(path_or_buffer, sep=";", dtype=str, encoding=enc, **kwargs)
        except (UnicodeDecodeError, pd.errors.ParserError, ValueError) as exc:
            last = exc
    raise RuntimeError(f"Не удалось прочитать CSV: {last}")


def _detect_test_tables(files: list[Path]) -> tuple[pd.DataFrame, pd.DataFrame]:
    notices = None
    tru = None
    candidates: list[tuple[str, bytes | Path]] = []
    for path in files:
        if path.suffix.lower() == ".csv":
            candidates.append((path.name, path))
        elif path.suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(path) as zf:
                    for name in zf.namelist():
                        if name.lower().endswith(".csv"):
                            candidates.append((Path(name).name, zf.read(name)))
            except zipfile.BadZipFile:
                continue

    for name, source in candidates:
        try:
            obj = io.BytesIO(source) if isinstance(source, bytes) else source
            sample = _read_csv_flexible(obj, nrows=5)
        except Exception:
            continue
        cols = {str(x).strip().casefold() for x in sample.columns}
        obj = io.BytesIO(source) if isinstance(source, bytes) else source
        if {"lot_id", "subject"}.issubset(cols) and notices is None:
            notices = _read_csv_flexible(obj)
            _log(f"Тестовые данные: таблица извещений → {name} ({len(notices):,} строк)")
        elif {"lot_id", "product_name", "okpd2_code"}.issubset(cols) and tru is None:
            tru = _read_csv_flexible(obj)
            _log(f"Тестовые данные: таблица ТРУ → {name} ({len(tru):,} строк)")
    if notices is None or tru is None:
        names = ", ".join(p.name for p in files)
        raise RuntimeError(
            "Не удалось определить обе тестовые таблицы по колонкам. "
            f"Найдены файлы: {names or 'нет файлов'}"
        )
    return notices, tru


def _dataset_path() -> Path | None:
    env = os.getenv("DATASET_PATH")
    candidates = [Path(env)] if env else []
    candidates += [ROOT / "datasets" / "source.zip"]
    return next((p for p in candidates if p and p.exists()), None)


def _winner_map_for_lots(lot_ids: set[str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    dataset = _dataset_path()
    if dataset:
        archive = DataArchive(dataset)
        try:
            for chunk in pd.read_csv(
                archive.open("Поставщики"), sep=";", dtype=str, chunksize=200_000,
                usecols=["lot_id", "supplier_inn", "is_winner"],
            ):
                chunk = chunk[(chunk["lot_id"].isin(lot_ids)) & (chunk["is_winner"].str.lower() == "true")]
                for row in chunk.itertuples(index=False):
                    lot = str(row.lot_id or "").strip()
                    inn = re.sub(r"\D", "", str(row.supplier_inn or ""))
                    if lot and len(inn) in (10, 12):
                        result[lot].append(inn)
        finally:
            archive.close()
    if result:
        return result

    # Fallback без исходного ZIP: используем уже сохранённую историю побед.
    app = create_app("dev")
    with app.app_context():
        rows = SupplierContract.query.filter(SupplierContract.lot_id.in_(lot_ids)).all()
        for contract in rows:
            if contract.is_winner and contract.supplier and contract.lot_id:
                result[str(contract.lot_id)].append(str(contract.supplier.inn))
    return result


def _clean(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    value = str(value).strip()
    return "" if value.casefold() == "nan" else value


def build_history_profiles(notices: pd.DataFrame, tru: pd.DataFrame) -> tuple[dict[str, dict], list[dict]]:
    notices = notices.copy()
    tru = tru.copy()
    notices["lot_id"] = notices["lot_id"].astype(str)
    tru["lot_id"] = tru["lot_id"].astype(str)
    lots = set(notices["lot_id"].dropna()) | set(tru["lot_id"].dropna())
    winners = _winner_map_for_lots(lots)
    if not winners:
        raise RuntimeError("Не удалось связать тестовые lot_id с победителями из Поставщики_24-25")

    notice_by_lot: dict[str, dict] = {}
    for row in notices.to_dict("records"):
        lot = _clean(row.get("lot_id"))
        if lot:
            notice_by_lot[lot] = row

    tru_by_lot: dict[str, list[dict]] = defaultdict(list)
    for row in tru.to_dict("records"):
        lot = _clean(row.get("lot_id"))
        if lot:
            tru_by_lot[lot].append(row)

    profiles: dict[str, dict] = defaultdict(lambda: {"subjects": [], "products": [], "okpd2": []})
    contracts: list[dict] = []
    for lot, inns in winners.items():
        notice = notice_by_lot.get(lot, {})
        subject = _clean(notice.get("subject") or notice.get("procedure_name"))
        amount = _clean(notice.get("start_price"))
        customer_inn = re.sub(r"\D", "", _clean(notice.get("customer_inn")))
        publish_date = _clean(notice.get("publish_date"))
        year = int(publish_date[:4]) if publish_date[:4].isdigit() else datetime.now().year
        items = tru_by_lot.get(lot) or [{}]
        primary = items[0]
        product = _clean(primary.get("product_name"))
        code = _clean(primary.get("okpd2_code"))
        for inn in inns:
            p = profiles[inn]
            if subject and subject not in p["subjects"]:
                p["subjects"].append(subject)
            for item in items:
                item_product = _clean(item.get("product_name"))
                item_code = _clean(item.get("okpd2_code"))
                if item_product and item_product not in p["products"]:
                    p["products"].append(item_product)
                if item_code and item_code not in p["okpd2"]:
                    p["okpd2"].append(item_code)
            contracts.append({
                "inn": inn,
                "lot_id": lot,
                "contract_number": _clean(notice.get("reqnum")) or lot,
                "year": year,
                "amount": float(amount.replace(",", ".")) if amount.replace(",", ".").replace(".", "", 1).isdigit() else 0.0,
                "subject": subject,
                "product_name": product,
                "okpd2_code": code,
                "customer_inn": customer_inn or None,
            })

    compact: dict[str, dict] = {}
    for inn, p in profiles.items():
        compact[inn] = {
            "subjects": p["subjects"][:20],
            "products": p["products"][:30],
            "okpd2": p["okpd2"][:40],
            "history_text": (
                "Опыт закупок: " + "; ".join(p["subjects"][:10]) +
                ". Товары/услуги: " + "; ".join(p["products"][:18]) +
                ". ОКПД2: " + ", ".join(p["okpd2"][:30])
            )[:8000],
        }
    _log(f"Тестовые данные: профили собраны для {len(compact):,} ИНН; новых исторических связей {len(contracts):,}")
    return compact, contracts


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _cache_fresh(entry: dict) -> bool:
    checked = entry.get("checked_at")
    if not checked:
        return False
    try:
        return datetime.fromisoformat(checked) >= datetime.now() - timedelta(days=CACHE_TTL_DAYS)
    except (TypeError, ValueError):
        return False


def _dadata_lookup(inn: str, token: str) -> tuple[str, dict | None, str | None]:
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    last_error = None
    for attempt in range(3):
        try:
            r = requests.post(DADATA_URL, headers=headers, json={"query": inn}, timeout=DADATA_TIMEOUT)
            if r.status_code == 429:
                last_error = "HTTP 429"
                time.sleep(0.7 * (attempt + 1))
                continue
            if r.status_code in (401, 403):
                return inn, None, f"HTTP {r.status_code}: проверьте DADATA_TOKEN"
            if r.status_code >= 500:
                last_error = f"HTTP {r.status_code}"
                time.sleep(0.5 * (attempt + 1))
                continue
            r.raise_for_status()
            suggestions = (r.json() or {}).get("suggestions") or []
            if not suggestions:
                return inn, {"not_found": True}, None
            data = suggestions[0].get("data") or {}
            address = data.get("address") or {}
            state = data.get("state") or {}
            name = data.get("name") or {}
            payload = {
                "name": name.get("short_with_opf") or suggestions[0].get("value") or "",
                "ogrn": data.get("ogrn") or "",
                "primary_okved": data.get("okved") or "",
                "status": state.get("status") or "",
                "region": (address.get("data") or {}).get("region_with_type") or "",
                "address": address.get("value") or "",
            }
            return inn, payload, None
        except (requests.RequestException, ValueError) as exc:
            last_error = str(exc)
            time.sleep(0.4 * (attempt + 1))
    return inn, None, last_error or "request error"


def fetch_dadata(inns: list[str], token: str) -> tuple[dict[str, dict], int]:
    cache = _load_json(DADATA_CACHE)
    result: dict[str, dict] = {}
    to_fetch: list[str] = []
    for inn in inns:
        entry = cache.get(inn) or {}
        if _cache_fresh(entry) and isinstance(entry.get("data"), dict):
            result[inn] = entry["data"]
        else:
            to_fetch.append(inn)

    _log(f"DaData: {len(result):,} ИНН взято из кэша; новых запросов {len(to_fetch):,}")
    errors = 0
    if to_fetch:
        # Один preflight-запрос не даёт отправить тысячи запросов с неверным токеном.
        first_inn = to_fetch[0]
        _, first_data, first_error = _dadata_lookup(first_inn, token)
        if first_error and ("401" in first_error or "403" in first_error):
            _log(f"DaData: авторизация отклонена ({first_error}); остальные запросы пропущены.")
            return result, len(to_fetch)
        if first_data is not None:
            result[first_inn] = first_data
            cache[first_inn] = {"checked_at": datetime.now().isoformat(timespec="seconds"), "data": first_data}
        else:
            errors += 1
        to_fetch = to_fetch[1:]

    if to_fetch:
        with ThreadPoolExecutor(max_workers=DADATA_WORKERS) as pool:
            futures = {pool.submit(_dadata_lookup, inn, token): inn for inn in to_fetch}
            for idx, future in enumerate(as_completed(futures), 1):
                inn = futures[future]
                try:
                    _, data, error = future.result()
                except Exception as exc:
                    data, error = None, str(exc)
                if data is not None:
                    result[inn] = data
                    cache[inn] = {"checked_at": datetime.now().isoformat(timespec="seconds"), "data": data}
                else:
                    errors += 1
                    if error and "401" in error or error and "403" in error:
                        # Неверный токен — бессмысленно отправлять оставшиеся запросы повторно,
                        # но уже запущенные futures безопасно завершатся.
                        pass
                if idx % 100 == 0 or idx == len(to_fetch):
                    _log(f"DaData: обработано {idx:,}/{len(to_fetch):,}; успешно {len(result):,}; ошибок {errors:,}")
                    _save_json(DADATA_CACHE, cache)
    _save_json(DADATA_CACHE, cache)
    return result, errors


def _merge_semicolon(existing: str | None, additions: list[str], limit: int = 8000) -> str:
    values: list[str] = []
    seen: set[str] = set()
    for raw in list(str(existing or "").split(";")) + list(additions):
        clean = re.sub(r"\s+", " ", str(raw or "")).strip(" ;")
        key = clean.casefold()
        if clean and key not in seen:
            values.append(clean)
            seen.add(key)
    out = "; ".join(values)
    return out[:limit]


def _merge_codes(existing: str | None, additions: list[str], limit: int = 50) -> str:
    out: list[str] = []
    seen: set[str] = set()
    for raw in list(str(existing or "").split(",")) + additions:
        code = str(raw or "").strip()
        if code and code not in seen:
            out.append(code)
            seen.add(code)
        if len(out) >= limit:
            break
    return ",".join(out)


def apply_to_database(profiles: dict[str, dict], contracts: list[dict], dadata: dict[str, dict]) -> dict:
    app = create_app("dev")
    with app.app_context():
        inns = sorted(set(profiles) | set(dadata))
        suppliers = Supplier.query.filter(Supplier.inn.in_(inns)).all() if inns else []
        by_inn = {str(s.inn): s for s in suppliers}
        now = datetime.utcnow()
        history_updated = 0
        dadata_updated = 0

        for inn, profile in profiles.items():
            supplier = by_inn.get(inn)
            if not supplier:
                continue
            additions = list(profile.get("subjects") or []) + list(profile.get("products") or [])
            supplier.specialization = _merge_semicolon(supplier.specialization, additions)
            supplier.okpd2_codes = _merge_codes(supplier.okpd2_codes, list(profile.get("okpd2") or []))
            supplier.unique_won_okpd2 = max(
                int(supplier.unique_won_okpd2 or 0),
                len(set(x for x in (profile.get("okpd2") or []) if x)),
            )
            supplier.enrichment_updated_at = now
            history_updated += 1

        for inn, data in dadata.items():
            supplier = by_inn.get(inn)
            if not supplier or data.get("not_found"):
                continue
            name = str(data.get("name") or "").strip()
            if name and (not supplier.name or supplier.name.startswith("Контрагент ИНН")):
                supplier.name = name
            if data.get("ogrn"):
                supplier.ogrn = str(data["ogrn"])[:15]
            if data.get("primary_okved"):
                supplier.primary_okved = str(data["primary_okved"])[:32]
            if data.get("region") and (not supplier.region or supplier.region == "Россия"):
                supplier.region = str(data["region"])[:128]
            if data.get("address"):
                supplier.address = str(data["address"])[:1000]
            if str(data.get("status") or "").upper() == "ACTIVE":
                supplier.is_verified = True
            supplier.enrichment_updated_at = now
            dadata_updated += 1

        # Новые тестовые победы дополняют историю, но не дублируются при повторном запуске.
        contract_inserted = 0
        for row in contracts:
            supplier = by_inn.get(row["inn"])
            if not supplier:
                continue
            exists = SupplierContract.query.filter_by(supplier_id=supplier.id, lot_id=row["lot_id"]).first()
            if exists:
                # Новые тестовые ТРУ могут уточнить старую запись.
                exists.subject = row.get("subject") or exists.subject
                exists.product_name = row.get("product_name") or exists.product_name
                exists.okpd2_code = row.get("okpd2_code") or exists.okpd2_code
                continue
            db.session.add(SupplierContract(
                supplier_id=supplier.id,
                contract_number=row.get("contract_number") or row["lot_id"],
                lot_id=row["lot_id"],
                year=int(row.get("year") or datetime.now().year),
                amount=float(row.get("amount") or 0),
                subject=row.get("subject"),
                product_name=row.get("product_name"),
                okpd2_code=row.get("okpd2_code"),
                customer_inn=row.get("customer_inn"),
                is_winner=True,
            ))
            supplier.wins_count = int(supplier.wins_count or 0) + 1
            supplier.participation_count = max(int(supplier.participation_count or 0) + 1, supplier.wins_count)
            contract_inserted += 1

        db.session.commit()
        return {
            "profiles_total": len(profiles),
            "profiles_matched": history_updated,
            "dadata_received": len(dadata),
            "dadata_matched": dadata_updated,
            "contracts_added": contract_inserted,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-url", default=os.getenv("YANDEX_TEST_DATA_URL", DEFAULT_YANDEX_URL))
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-dadata", action="store_true")
    args = parser.parse_args()

    started = datetime.now().isoformat(timespec="seconds")
    _write_status("running", "Загружаем тестовые данные и обогащаем компании…", started_at=started)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    files: list[Path] = []
    if not args.skip_download:
        try:
            _log(f"Yandex Disk: скачиваем тестовый набор {args.public_url}")
            files = download_yandex_dataset(args.public_url, DATA_DIR)
            _log(f"Yandex Disk: скачано/обновлено файлов: {len(files)}")
        except Exception as exc:
            _log(f"Yandex Disk: загрузка не удалась: {exc}")
    if not files:
        files = _cached_data_files(DATA_DIR)
        if files:
            _log(f"Тестовые данные: используем локальный кэш ({len(files)} файлов)")
    if not files:
        _write_status("error", "Тестовые данные не скачаны и локального кэша нет.")
        return 2

    try:
        notices, tru = _detect_test_tables(files)
        profiles, contracts = build_history_profiles(notices, tru)
    except Exception as exc:
        _write_status("error", f"Ошибка разбора тестовых данных: {exc}")
        raise

    token = (os.getenv("DADATA_TOKEN") or "").strip()
    dadata: dict[str, dict] = {}
    dadata_errors = 0
    dadata_skipped_reason = None
    if args.skip_dadata:
        dadata_skipped_reason = "отключено параметром"
    elif not token:
        dadata_skipped_reason = "DADATA_TOKEN не задан"
    elif DADATA_MAX_COMPANIES == 0:
        dadata_skipped_reason = "DADATA_MAX_COMPANIES=0"
    else:
        inns = sorted(profiles, key=lambda x: x)[:DADATA_MAX_COMPANIES]
        _log(f"DaData: обогащаем до {len(inns):,} компаний, workers={DADATA_WORKERS}")
        dadata, dadata_errors = fetch_dadata(inns, token)

    stats = apply_to_database(profiles, contracts, dadata)
    message = (
        f"Готово: тестовые профили {stats['profiles_matched']}/{stats['profiles_total']}, "
        f"DaData {stats['dadata_matched']}/{stats['dadata_received']}, "
        f"новых исторических записей {stats['contracts_added']}."
    )
    if dadata_skipped_reason:
        message += f" DaData пропущена: {dadata_skipped_reason}."
    _write_status(
        "ok",
        message,
        finished_at=datetime.now().isoformat(timespec="seconds"),
        files=[str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p) for p in files],
        dadata_errors=dadata_errors,
        **stats,
    )
    _log(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
