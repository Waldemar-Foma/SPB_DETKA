"""Обогащение локальной БД по XLSX реестру ГИСП/Минпромторга."""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import create_app  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import RegistrySync, Supplier  # noqa: E402


def _norm(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def pick_column(columns, needles):
    normalized = {c: _norm(c) for c in columns}
    for needle in needles:
        for original, low in normalized.items():
            if needle in low:
                return original
    return None


def _read_registry(path: Path) -> pd.DataFrame:
    """Находит лист и строку заголовка даже если формат XLSX ГИСП слегка поменялся."""
    xls = pd.ExcelFile(path, engine="openpyxl")
    diagnostics = []
    for sheet in xls.sheet_names:
        preview = pd.read_excel(xls, sheet_name=sheet, header=None, nrows=25, dtype=str)
        diagnostics.append(f"{sheet}: {preview.shape[0]} preview rows")
        for row_idx in range(len(preview)):
            values = [_norm(v) for v in preview.iloc[row_idx].tolist()]
            if any(v == "инн" or v.startswith("инн ") or "инн предприятия" in v or "инн производителя" in v for v in values):
                df = pd.read_excel(xls, sheet_name=sheet, header=row_idx, dtype=str)
                if pick_column(df.columns, ["инн"]):
                    print(f"ГИСП: найден лист {sheet!r}, строка заголовка Excel {row_idx + 1}", flush=True)
                    return df

    # Иногда заголовок уже первая строка, но preview получил необычные merged cells.
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet, dtype=str)
        if pick_column(df.columns, ["инн"]):
            print(f"ГИСП: найден лист {sheet!r} со стандартным заголовком", flush=True)
            return df

    raise RuntimeError("Не удалось найти таблицу с колонкой ИНН. Просмотрены листы: " + "; ".join(diagnostics))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, type=Path)
    args = ap.parse_args()

    started = datetime.utcnow()
    app = create_app("dev")
    try:
        if not args.file.exists() or args.file.stat().st_size < 2_000:
            raise RuntimeError(f"Файл реестра отсутствует или слишком мал: {args.file}")

        df = _read_registry(args.file)
        inn_col = pick_column(df.columns, ["инн"])
        name_col = pick_column(df.columns, ["наименование предприятия", "наименование организации", "наименование производителя", "наименование"])
        if not inn_col:
            raise RuntimeError(f"Не найдена колонка ИНН. Колонки: {list(df.columns)}")

        type_col = pick_column(df.columns, ["тип выгрузки", "coverage type"])
        source_col = pick_column(df.columns, ["источник", "source"])
        partial_mirror = False
        if type_col:
            partial_mirror = df[type_col].astype(str).str.contains("partial-mirror", case=False, na=False).any()
        if source_col and not partial_mirror:
            partial_mirror = df[source_col].astype(str).str.contains("tovarminpro", case=False, na=False).any()

        registry: dict[str, str] = {}
        for row in df.itertuples(index=False, name=None):
            data = dict(zip(df.columns, row))
            inn = re.sub(r"\D", "", str(data.get(inn_col, "") or ""))
            if len(inn) not in (10, 12):
                continue
            name = str(data.get(name_col, "") or "").strip() if name_col else ""
            registry[inn] = name

        if not registry:
            raise RuntimeError("В XLSX не найдено ни одного корректного ИНН")

        with app.app_context():
            now = datetime.utcnow()
            suppliers = Supplier.query.all()
            local_by_inn = {str(s.inn): s for s in suppliers if s.inn}

            # Только официальная полная XLSX считается снимком всего реестра.
            # Fallback-зеркало проверяет ограниченный FAISS-пул и поэтому не имеет права
            # сбрасывать ранее подтверждённые статусы производителей.
            if not partial_mirror:
                for supplier in suppliers:
                    supplier.is_gisp_manufacturer = False
            else:
                print("ГИСП: применяем частичную fallback-выгрузку — ранее подтверждённые статусы не сбрасываются", flush=True)

            updated = 0
            for inn, name in registry.items():
                supplier = local_by_inn.get(inn)
                if not supplier:
                    continue
                supplier.is_gisp_manufacturer = True
                supplier.company_type = "Производитель"
                if name and (not supplier.name or supplier.name.startswith("Контрагент ИНН")):
                    supplier.name = name
                supplier.is_verified = True
                supplier.enrichment_updated_at = now
                updated += 1

            db.session.add(RegistrySync(
                source=("ГИСП fallback / публичное зеркало" if partial_mirror else "ГИСП / Минпромторг"),
                status="ok",
                rows_total=len(registry),
                matched_suppliers=updated,
                file_path=str(args.file),
                message=(
                    ("Частичное fallback-обогащение; " if partial_mirror else "")
                    + f"завершено за {(datetime.utcnow()-started).total_seconds():.1f} с"
                ),
                finished_at=datetime.utcnow(),
            ))
            db.session.commit()

        print(f"ГИСП: уникальных ИНН в реестре: {len(registry):,}; совпало с локальной БД: {updated:,}", flush=True)
        print("Данные доступны в веб-интерфейсе после обновления страницы.", flush=True)
    except Exception as exc:
        with app.app_context():
            db.session.add(RegistrySync(
                source="ГИСП / Минпромторг",
                status="error",
                rows_total=0,
                matched_suppliers=0,
                file_path=str(args.file),
                message=str(exc)[:1000],
                finished_at=datetime.utcnow(),
            ))
            db.session.commit()
        raise


if __name__ == "__main__":
    main()
