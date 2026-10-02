from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import func

from backend.extensions import db
from backend.models import Procurement, Supplier
from backend.services.role_classifier import procurement_kind
from backend.services.geography import approx_supplier_coords

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARCHIVE = ROOT / "datasets" / "dataset.zip"
STATE_FILE = ROOT / "instance" / "active_dataset.json"
DATASET_COUNT = 4
SUPPLIER_SOURCE = "dataset_suppliers_24_25"
SUPPLIER_MAP = ROOT / "ml_artifacts" / "supplier_index_map.csv"


def _decode_name(name: str) -> str:
    """Decode #U041f-style names while leaving normal ZIP names untouched."""
    return re.sub(r"#U([0-9A-Fa-f]{4})", lambda m: chr(int(m.group(1), 16)), name)


def _as_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")


def _dataset_members(archive_path: Path, dataset_id: int) -> tuple[str, str]:
    if dataset_id not in range(1, DATASET_COUNT + 1):
        raise ValueError(f"Номер датасета должен быть от 1 до {DATASET_COUNT}")
    if not archive_path.exists():
        raise FileNotFoundError(f"Не найден архив: {archive_path}")

    notice = product = None
    suffix = f"_{dataset_id}.csv"
    with zipfile.ZipFile(archive_path) as zf:
        for raw_name in zf.namelist():
            decoded = _decode_name(raw_name)
            base = Path(decoded).name
            if not base.endswith(suffix):
                continue
            low = base.casefold()
            if "извещения" in low:
                notice = raw_name
            elif "потоварка" in low:
                product = raw_name

    if not notice or not product:
        raise FileNotFoundError(
            f"В dataset.zip не найдена полная пара Извещения_{dataset_id} + Потоварка_{dataset_id}"
        )
    return notice, product


def _read_rows(zf: zipfile.ZipFile, member: str) -> list[dict[str, str]]:
    text = _as_text(zf.read(member))
    reader = csv.reader(io.StringIO(text), delimiter=";")
    try:
        header = next(reader)
    except StopIteration:
        return []

    header = [h.strip().strip('"') for h in header]
    # В первой части исходника заголовок содержит опечатку: два поля слиты в
    # "reqnum;procedure_name", хотя строки содержат 11 отдельных значений.
    if "reqnum;procedure_name" in header:
        idx = header.index("reqnum;procedure_name")
        header = header[:idx] + ["reqnum", "procedure_name"] + header[idx + 1 :]

    rows: list[dict[str, str]] = []
    for values in reader:
        if not values or not any(str(v).strip() for v in values):
            continue
        if len(values) < len(header):
            values += [""] * (len(header) - len(values))
        elif len(values) > len(header):
            values = values[: len(header)]
        rows.append({key: str(value).strip() for key, value in zip(header, values)})
    return rows


def _float(value: str | None) -> float:
    try:
        return float(str(value or "0").replace(" ", "").replace(",", "."))
    except ValueError:
        return 0.0


def _date(value: str | None):
    value = str(value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value[:10], fmt).date()
        except ValueError:
            pass
    return None


def _region_from_kpp(kpp: str | None) -> str:
    prefix = str(kpp or "")[:2]
    return {"78": "Санкт-Петербург", "47": "Ленинградская область"}.get(prefix, "Санкт-Петербург")




def _supplier_member(archive_path: Path) -> str:
    """Return the common supplier-history CSV stored inside dataset.zip."""
    with zipfile.ZipFile(archive_path) as zf:
        for raw_name in zf.namelist():
            base = Path(_decode_name(raw_name)).name.casefold()
            if base.startswith("поставщики") and base.endswith(".csv"):
                return raw_name
    raise FileNotFoundError("В dataset.zip не найден общий файл Поставщики_24-25.csv")


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "да"}


def _valid_inn(value: str | None) -> str:
    inn = re.sub(r"\D", "", str(value or ""))
    return inn if len(inn) in {10, 12} else ""


def _supplier_profiles() -> dict[str, dict]:
    """Load the 2k semantic profiles used by the bundled FAISS model.

    This makes the imported counterparties useful for matching immediately,
    while company names/contacts can still be enriched later by the existing
    enrichment parser.
    """
    if not SUPPLIER_MAP.exists():
        return {}
    profiles: dict[str, dict] = {}
    with SUPPLIER_MAP.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            inn = _valid_inn(row.get("supplier_inn"))
            if not inn:
                continue
            source = (row.get("ai_embedding_source") or "").strip()
            codes = ""
            if source.startswith("ОКПД2:"):
                head = source.split("|", 1)[0].replace("ОКПД2:", "", 1).strip()
                codes = ",".join(x for x in head.split() if x)
            profiles[inn] = {
                "specialization": source or None,
                "okpd2_codes": codes or None,
                "company_type": (row.get("estimated_role") or "Поставщик").strip() or "Поставщик",
                "participation_count": int(float(row.get("total_participations") or 0)),
                "wins_count": int(float(row.get("total_wins") or 0)),
            }
    return profiles


def ensure_suppliers(archive_path: Path = DEFAULT_ARCHIVE) -> dict:
    """Import the common 2024-25 counterparty history into the live Supplier table.

    The supplier file is historical and therefore is shared by all four 2026
    notice/product datasets; it is not joined to current lots by lot_id.  It
    supplies the candidate pool and participation/win statistics for matching.
    """
    member = _supplier_member(archive_path)
    stats: dict[str, dict] = {}
    rows_total = 0
    with zipfile.ZipFile(archive_path) as zf:
        text = io.TextIOWrapper(zf.open(member), encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text, delimiter=";")
        for row in reader:
            rows_total += 1
            inn = _valid_inn(row.get("supplier_inn"))
            if not inn:
                continue
            item = stats.get(inn)
            if item is None:
                item = {"participation_count": 0, "wins_count": 0, "kpp": ""}
                stats[inn] = item
            item["participation_count"] += 1
            if _truthy(row.get("is_winner")):
                item["wins_count"] += 1
            if not item["kpp"]:
                item["kpp"] = re.sub(r"\D", "", str(row.get("supplier_kpp") or ""))

    profiles = _supplier_profiles()
    existing = {s.inn: s for s in Supplier.query.filter(Supplier.inn.in_(list(stats))).all()}
    inserted = 0
    updated = 0
    batch: list[dict] = []

    for inn, item in stats.items():
        profile = profiles.get(inn, {})
        participations = max(int(item["participation_count"]), int(profile.get("participation_count") or 0))
        wins = max(int(item["wins_count"]), int(profile.get("wins_count") or 0))
        region = _region_from_kpp(item.get("kpp"))
        supplier = existing.get(inn)
        if supplier is not None:
            supplier.participation_count = participations
            supplier.wins_count = wins
            if not supplier.region:
                supplier.region = region
            if supplier.lat is None or supplier.lon is None:
                supplier.lat, supplier.lon = approx_supplier_coords(inn, supplier.region or region)
            if profile.get("specialization") and not supplier.specialization:
                supplier.specialization = profile["specialization"]
            if profile.get("okpd2_codes") and not supplier.okpd2_codes:
                supplier.okpd2_codes = profile["okpd2_codes"]
            if profile.get("company_type") and (not supplier.company_type or supplier.company_type == "Поставщик"):
                supplier.company_type = profile["company_type"]
            # Never overwrite a name/contact already found by enrichment.
            if not supplier.data_source or supplier.data_source == "demo":
                supplier.data_source = SUPPLIER_SOURCE
            updated += 1
            continue

        lat, lon = approx_supplier_coords(inn, region)
        batch.append({
            "inn": inn,
            "name": f"Контрагент ИНН {inn}",
            "company_type": profile.get("company_type") or "Поставщик",
            "region": region,
            "lat": lat,
            "lon": lon,
            "is_verified": True,
            "is_gisp_manufacturer": False,
            "is_sme": False,
            "data_source": SUPPLIER_SOURCE,
            "participation_count": participations,
            "wins_count": wins,
            "unique_won_okpd2": 0,
            "specialization": profile.get("specialization"),
            "okpd2_codes": profile.get("okpd2_codes"),
        })
        if len(batch) >= 2000:
            db.session.bulk_insert_mappings(Supplier, batch)
            inserted += len(batch)
            batch.clear()

    if batch:
        db.session.bulk_insert_mappings(Supplier, batch)
        inserted += len(batch)
    db.session.commit()
    return {
        "file": Path(_decode_name(member)).name,
        "rows": rows_total,
        "unique_suppliers": len(stats),
        "inserted": inserted,
        "updated": updated,
        "semantic_profiles": sum(1 for inn in stats if inn in profiles),
    }


def inspect_datasets(archive_path: Path = DEFAULT_ARCHIVE) -> list[dict]:
    result = []
    with zipfile.ZipFile(archive_path) as zf:
        for dataset_id in range(1, DATASET_COUNT + 1):
            notice, product = _dataset_members(archive_path, dataset_id)
            notices = _read_rows(zf, notice)
            products = _read_rows(zf, product)
            result.append({
                "id": dataset_id,
                "notices": len(notices),
                "products": len(products),
                "notice_file": Path(_decode_name(notice)).name,
                "product_file": Path(_decode_name(product)).name,
            })
    return result


def active_dataset() -> dict:
    if not STATE_FILE.exists():
        return {"id": None, "label": "не выбран", "updated_at": None}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"id": None, "label": "не определён", "updated_at": None}


def switch_dataset(dataset_id: int, archive_path: Path = DEFAULT_ARCHIVE) -> dict:
    notice_member, product_member = _dataset_members(archive_path, dataset_id)
    supplier_state = ensure_suppliers(archive_path)
    with zipfile.ZipFile(archive_path) as zf:
        notices = _read_rows(zf, notice_member)
        products = _read_rows(zf, product_member)

    product_by_lot: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in products:
        lot_id = row.get("lot_id", "").strip()
        if lot_id:
            product_by_lot[lot_id].append(row)

    # Пользовательские заявки не трогаем. Меняется только импортированный
    # закупочный набор, который служит демонстрационным/поисковым контекстом.
    imported = Procurement.query.filter(func.upper(func.coalesce(Procurement.source_system, "")) != "USER").all()
    removed = len(imported)
    for procurement in imported:
        db.session.delete(procurement)
    db.session.flush()

    existing_numbers = {
        row[0] for row in db.session.query(Procurement.procurement_number).all() if row[0]
    }
    inserted = 0
    for row in notices:
        lot_id = row.get("lot_id", "").strip()
        if not lot_id:
            continue
        product_rows = product_by_lot.get(lot_id, [])
        first_product = product_rows[0] if product_rows else {}
        product_names = []
        seen_names = set()
        for item in product_rows:
            name = (item.get("product_name") or "").strip()
            if name and name not in seen_names:
                product_names.append(name)
                seen_names.add(name)
        product_text = "; ".join(product_names[:12])
        procedure_name = (row.get("procedure_name") or "").strip()
        subject = (row.get("subject") or "").strip()
        number = lot_id if lot_id not in existing_numbers else f"DS{dataset_id}-{lot_id}"
        existing_numbers.add(number)
        region = _region_from_kpp(row.get("customer_kpp"))

        procurement = Procurement(
            procurement_number=number,
            title=procedure_name or subject or product_text or f"Закупка {lot_id}",
            subject=subject or procedure_name or product_text,
            okpd2_code=(first_product.get("okpd2_code") or "").strip() or None,
            okpd2_name=(first_product.get("product_name") or "").strip() or None,
            region=region,
            delivery_region=region,
            initial_price=_float(row.get("start_price")),
            keywords=product_text or subject or procedure_name,
            customer_inn=(row.get("customer_inn") or "").strip() or None,
            customer_kpp=(row.get("customer_kpp") or "").strip() or None,
            source_system=(row.get("is_eshop_or_aisgz") or "DATASET").strip() or "DATASET",
            is_smp=(row.get("is_smp") or "").strip().lower() in {"true", "1", "yes", "да"},
            publish_date=_date(row.get("publish_date")),
            input_mode="spec",
            status="matching",
        )
        procurement.procurement_kind = procurement_kind(procurement)
        db.session.add(procurement)
        inserted += 1

    db.session.commit()
    state = {
        "id": dataset_id,
        "label": f"Датасет {dataset_id}",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "notices": len(notices),
        "products": len(products),
        "inserted": inserted,
        "removed": removed,
        "notice_file": Path(_decode_name(notice_member)).name,
        "product_file": Path(_decode_name(product_member)).name,
        "suppliers": supplier_state,
    }
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state
