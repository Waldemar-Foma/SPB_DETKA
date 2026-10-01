"""Универсальный офлайн-импорт реквизитов/ОКВЭД/МСП из подготовленного CSV.

Ожидаемые колонки: inn,name,primary_okved,is_sme,address,ogrn (часть опциональна).
Так можно один раз выгрузить данные из Прозрачного бизнеса/реестра МСП и не
делать network-call во время демонстрации.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import create_app  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import Supplier  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', required=True, type=Path)
    args = ap.parse_args()
    df = pd.read_csv(args.file, dtype=str).fillna('')
    if 'inn' not in df.columns:
        raise SystemExit('Нужна колонка inn')
    rows = {str(r.inn).strip(): r for r in df.itertuples(index=False)}
    app = create_app('dev')
    updated = 0
    with app.app_context():
        for s in Supplier.query.all():
            r = rows.get(s.inn)
            if not r: continue
            for field in ('name', 'primary_okved', 'address', 'ogrn'):
                if hasattr(r, field) and getattr(r, field): setattr(s, field, getattr(r, field))
            if hasattr(r, 'is_sme'):
                s.is_sme = str(r.is_sme).lower() in {'1','true','yes','да'}
            s.is_verified = True
            s.enrichment_updated_at = datetime.utcnow()
            updated += 1
        db.session.commit()
    print(f'Обогащено компаний: {updated}')

if __name__ == '__main__': main()
