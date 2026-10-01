"""Обогащение локальной БД по уже скачанному registry.xlsx ГИСП.

После завершения результат сразу доступен в веб-интерфейсе на странице
«Контрагенты»: поля is_gisp_manufacturer/enrichment_updated_at и журнал
registry_syncs читаются сайтом напрямую из той же SQLite/PostgreSQL БД.
"""
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


def pick_column(columns, needles):
    normalized = {c: re.sub(r'\s+', ' ', str(c).lower()).strip() for c in columns}
    for needle in needles:
        for original, low in normalized.items():
            if needle in low:
                return original
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', required=True, type=Path)
    args = ap.parse_args()

    started = datetime.utcnow()
    try:
        df = pd.read_excel(args.file, dtype=str)
        inn_col = pick_column(df.columns, ['инн'])
        name_col = pick_column(df.columns, ['наименование предприятия', 'наименование организации', 'наименование'])
        if not inn_col:
            raise RuntimeError(f'Не найдена колонка ИНН. Колонки: {list(df.columns)}')

        registry = {}
        for r in df.itertuples(index=False, name=None):
            row = dict(zip(df.columns, r))
            inn = re.sub(r'\D', '', str(row.get(inn_col, '') or ''))
            if inn:
                registry[inn] = str(row.get(name_col, '') or '').strip() if name_col else ''

        app = create_app('dev')
        updated = 0
        with app.app_context():
            now = datetime.utcnow()
            suppliers = Supplier.query.all()
            # Реестр считается снимком на момент синхронизации: устаревшие флаги
            # прошлого запуска не должны оставаться «вечными производителями».
            for supplier in suppliers:
                supplier.is_gisp_manufacturer = False
            for supplier in suppliers:
                if supplier.inn in registry:
                    supplier.is_gisp_manufacturer = True
                    supplier.company_type = 'Производитель'
                    if registry[supplier.inn] and supplier.name.startswith('Контрагент ИНН'):
                        supplier.name = registry[supplier.inn]
                    supplier.is_verified = True
                    supplier.enrichment_updated_at = now
                    updated += 1

            db.session.add(RegistrySync(
                source='ГИСП / Минпромторг',
                status='ok',
                rows_total=len(registry),
                matched_suppliers=updated,
                file_path=str(args.file),
                message=f'Обогащение завершено за {(datetime.utcnow()-started).total_seconds():.1f} с',
                finished_at=datetime.utcnow(),
            ))
            db.session.commit()
        print(f'ГИСП: строк в реестре: {len(registry)}; отмечено производителей в локальном пуле: {updated}')
        print('Данные уже доступны на /suppliers/ после обновления страницы.')
    except Exception as exc:
        app = create_app('dev')
        with app.app_context():
            db.session.add(RegistrySync(
                source='ГИСП / Минпромторг',
                status='error',
                rows_total=0,
                matched_suppliers=0,
                file_path=str(args.file),
                message=str(exc)[:1000],
                finished_at=datetime.utcnow(),
            ))
            db.session.commit()
        raise


if __name__ == '__main__':
    main()
