"""Сборка рабочей локальной БД из исходных CSV хакатона.

Поддерживает как прямой ZIP с CSV, так и внешний ZIP, внутри которого лежит
``Данные 24-25.zip``. Пул контрагентов собирается по всей России, а
закупочные контексты исходного кейса остаются привязаны к заказчикам СПб/ЛО.
География поставщика определяется по первым двум цифрам КПП и используется
как фактор ранжирования, а не как жёсткий фильтр.

Пример:
    python scripts/build_real_db.py --dataset "RLT.Uni_СПБ_1-2_10_2026.zip"

Перед запуском:
    pip install -r requirements.txt -r requirements-data.txt
"""
from __future__ import annotations

import argparse
import io
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from backend.extensions import db  # noqa: E402
from backend.models import Procurement, Supplier, SupplierContract, User  # noqa: E402
from backend.services.role_classifier import procurement_kind  # noqa: E402
from backend.services.geography import region_from_kpp, approx_supplier_coords  # noqa: E402
from backend.services.demo_users import ensure_admin_user  # noqa: E402

LOCAL_PREFIX_TO_REGION = {"78": "Санкт-Петербург", "47": "Ленинградская область"}


@dataclass
class Profile:
    participation_count: int = 0
    wins_count: int = 0
    region_votes: Counter = field(default_factory=Counter)
    okpd: Counter = field(default_factory=Counter)
    won_okpd: set[str] = field(default_factory=set)
    products: list[str] = field(default_factory=list)
    product_seen: set[str] = field(default_factory=set)


class DataArchive:
    """ZIP reader for the hackathon dataset.

    The supplied archive was created by a Windows archiver that stores the
    Cyrillic CSV file names in CP866 *without* the ZIP UTF-8 flag.  Python
    3.11 therefore decodes those names as CP437 by default inside Docker and
    strings such as ``Поставщики_24-25.csv`` become mojibake.  The CSV
    contents themselves are UTF-8; only the ZIP metadata needs CP866.

    Explicit ``metadata_encoding='cp866'`` keeps this deterministic on the
    Python 3.11 image used by Docker while still working for entries that do
    carry the UTF-8 flag (for those, zipfile ignores metadata_encoding).
    """

    @staticmethod
    def _open_zip(source):
        try:
            return zipfile.ZipFile(source, metadata_encoding='cp866')
        except TypeError:
            # Compatibility with Python versions older than 3.11.
            return zipfile.ZipFile(source)

    def __init__(self, path: Path):
        self.outer = self._open_zip(path)
        names = self.outer.namelist()
        csv_names = [n for n in names if n.lower().endswith('.csv')]
        self._inner_bytes = None
        if csv_names:
            self.data = self.outer
            print('[dataset] CSV найдены прямо во внешнем ZIP.')
        else:
            inner_name = next((n for n in names if n.lower().endswith('.zip')), None)
            if not inner_name:
                raise RuntimeError(
                    'В ZIP не найдены CSV или вложенный ZIP. '
                    f'Содержимое архива: {names[:20]}'
                )
            print(f'[dataset] Найден вложенный ZIP: {inner_name}')
            self._inner_bytes = self.outer.read(inner_name)
            self.data = self._open_zip(io.BytesIO(self._inner_bytes))

        available = [Path(n).name for n in self.data.namelist() if not n.endswith('/')]
        print('[dataset] Файлы данных: ' + ', '.join(available[:20]))

    def find(self, needle: str) -> str:
        low = needle.casefold()
        for name in self.data.namelist():
            if low in Path(name).name.casefold():
                return name
        available = [Path(n).name for n in self.data.namelist() if not n.endswith('/')]
        raise FileNotFoundError(
            f'Не найден файл набора данных по маркеру {needle!r}. '
            f'Доступные файлы: {available}'
        )

    def open(self, needle: str):
        return self.data.open(self.find(needle))

    def close(self):
        if self.data is not self.outer:
            self.data.close()
        self.outer.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', required=True, type=Path)
    parser.add_argument('--procurement-limit', type=int, default=1500)
    parser.add_argument('--contracts-per-supplier', type=int, default=50)
    args = parser.parse_args()

    archive = DataArchive(args.dataset)
    try:
        profiles, lot_entries = read_suppliers(archive)
        lot_meta = read_notices(archive, set(lot_entries))
        lot_tru = read_tru(archive, lot_entries, profiles)
        write_db(profiles, lot_entries, lot_meta, lot_tru, args)
    finally:
        archive.close()


def read_suppliers(archive: DataArchive):
    print('[1/4] Поставщики: общероссийский пул и агрегация...')
    profiles: dict[str, Profile] = defaultdict(Profile)
    lot_entries: dict[str, list[tuple[str, bool]]] = defaultdict(list)

    for chunk in pd.read_csv(
        archive.open('Поставщики'), sep=';', dtype=str, chunksize=200_000,
        usecols=['lot_id', 'supplier_inn', 'supplier_kpp', 'is_winner'],
    ):
        for row in chunk.itertuples(index=False):
            inn = str(row.supplier_inn or '').strip()
            lot = str(row.lot_id or '').strip()
            kpp = str(row.supplier_kpp or '')
            if not inn or not lot:
                continue
            is_winner = str(row.is_winner).lower() == 'true'
            p = profiles[inn]
            p.participation_count += 1
            p.wins_count += int(is_winner)
            p.region_votes[region_from_kpp(kpp)] += 1
            lot_entries[lot].append((inn, is_winner))

    print(f'    уникальных ИНН по РФ: {len(profiles):,}; лотов: {len(lot_entries):,}')
    return profiles, lot_entries


def read_notices(archive: DataArchive, local_lots: set[str]):
    print('[2/4] Извещения: метаданные лотов...')
    result = {}
    cols = ['publish_date', 'lot_id', 'start_price', 'reqnum', 'procedure_name', 'subject',
            'is_smp', 'customer_inn', 'customer_kpp', 'is_eshop_or_aisgz']
    for chunk in pd.read_csv(archive.open('Извещения'), sep=';', dtype=str,
                             chunksize=150_000, usecols=cols):
        chunk = chunk[chunk['lot_id'].isin(local_lots)]
        customer_prefix = chunk['customer_kpp'].fillna('').str[:2]
        chunk = chunk[customer_prefix.isin(LOCAL_PREFIX_TO_REGION)]
        for r in chunk.itertuples(index=False):
            result[str(r.lot_id)] = {
                'publish_date': str(r.publish_date or ''),
                'start_price': _float(r.start_price),
                'reqnum': _clean(r.reqnum),
                'title': _clean(r.procedure_name) or _clean(r.subject) or f'Лот {r.lot_id}',
                'subject': _clean(r.subject),
                'is_smp': str(r.is_smp).lower() == 'true',
                'customer_inn': _clean(r.customer_inn),
                'customer_kpp': _clean(r.customer_kpp),
                'source_system': _clean(r.is_eshop_or_aisgz),
            }
    print(f'    найдено извещений: {len(result):,}')
    return result


def read_tru(archive: DataArchive, lot_entries, profiles):
    print('[3/4] ТРУ: формирование специализаций и ОКПД2...')
    lot_tru: dict[str, tuple[str, str]] = {}
    for chunk in pd.read_csv(
        archive.open('ТРУ'), sep=';', dtype=str, chunksize=250_000,
        usecols=['lot_id', 'product_name', 'okpd2_code'],
    ):
        chunk = chunk[chunk['lot_id'].isin(lot_entries)]
        for r in chunk.itertuples(index=False):
            lot = str(r.lot_id)
            name = _clean(r.product_name)
            code = _clean(r.okpd2_code)
            if lot not in lot_tru and (code or name):
                lot_tru[lot] = (code, name)
            for inn, is_winner in lot_entries.get(lot, ()):  # обычно 1–2 записи
                p = profiles[inn]
                if code:
                    p.okpd[code] += 1
                    if is_winner:
                        p.won_okpd.add(code)
                if name and len(p.products) < 12 and name not in p.product_seen:
                    p.products.append(name[:240])
                    p.product_seen.add(name)
    print(f'    ТРУ-профили сформированы для {sum(bool(p.okpd) for p in profiles.values()):,} компаний')
    return lot_tru


def write_db(profiles, lot_entries, lot_meta, lot_tru, args):
    print('[4/4] Запись SQLite...')
    app = create_app('dev')
    with app.app_context():
        preserved_users = []
        try:
            for user in User.query.filter(~User.email.like('%@demo.local')).all():
                preserved_users.append({
                    'email': user.email, 'password_hash': user.password_hash, 'full_name': user.full_name,
                    'account_role': user.account_role, 'organization_inn': user.organization_inn,
                    'organization_name': user.organization_name, 'is_active': user.is_active,
                    'created_at': user.created_at, 'last_login_at': user.last_login_at,
                })
        except Exception:
            db.session.rollback()
            preserved_users = []

        db.drop_all()
        db.create_all()

        supplier_by_inn = {}
        for idx, (inn, p) in enumerate(profiles.items(), 1):
            region = p.region_votes.most_common(1)[0][0] if p.region_votes else 'Россия'
            top_codes = [c for c, _ in p.okpd.most_common(20)]
            lat, lon = approx_supplier_coords(inn, region)
            supplier = Supplier(
                inn=inn,
                name=f'Контрагент ИНН {inn}',
                company_type='Поставщик',
                region=region,
                lat=lat,
                lon=lon,
                okpd2_codes=','.join(top_codes),
                specialization='; '.join(p.products),
                participation_count=p.participation_count,
                wins_count=p.wins_count,
                unique_won_okpd2=len(p.won_okpd),
                data_source='hackathon_24_25',
                is_verified=False,
            )
            db.session.add(supplier)
            supplier_by_inn[inn] = supplier
            if idx % 2000 == 0:
                db.session.flush()
            if idx % 5000 == 0:
                print(f'      поставщики: {idx:,} / {len(profiles):,}', flush=True)
        db.session.flush()
        print(f'      поставщики: {len(profiles):,} / {len(profiles):,}', flush=True)

        # Исторические победы пишем bulk-вставками. Полные participation_count /
        # wins_count уже сохранены в Supplier, а здесь держим до N конкретных
        # кейсов на компанию для объяснимости и опыта с заказчиком.
        inserted_per_supplier = Counter()
        contract_batch = []
        contract_total = 0
        for lot, entries in lot_entries.items():
            meta = lot_meta.get(lot)
            if not meta:
                continue
            code, product = lot_tru.get(lot, ('', ''))
            year = _year(meta['publish_date'])
            for inn, is_winner in entries:
                if not is_winner or inserted_per_supplier[inn] >= args.contracts_per_supplier:
                    continue
                supplier = supplier_by_inn.get(inn)
                if not supplier:
                    continue
                contract_batch.append({
                    'supplier_id': supplier.id,
                    'contract_number': meta['reqnum'] or lot,
                    'lot_id': lot,
                    'year': year,
                    'amount': meta['start_price'],
                    'subject': meta['subject'] or meta['title'],
                    'product_name': product,
                    'okpd2_code': code,
                    'customer_inn': meta['customer_inn'],
                    'is_winner': True,
                })
                inserted_per_supplier[inn] += 1
                if len(contract_batch) >= 10_000:
                    db.session.bulk_insert_mappings(SupplierContract, contract_batch)
                    contract_total += len(contract_batch)
                    contract_batch.clear()
                    print(f'      история побед: {contract_total:,}', flush=True)
        if contract_batch:
            db.session.bulk_insert_mappings(SupplierContract, contract_batch)
            contract_total += len(contract_batch)
            contract_batch.clear()
        print(f'      история побед: {contract_total:,} — готово', flush=True)

        chosen_lots = choose_procurements(lot_meta, lot_tru, args.procurement_limit)
        for proc_idx, lot in enumerate(chosen_lots, 1):
            meta = lot_meta[lot]
            code, product = lot_tru.get(lot, ('', ''))
            if not code:
                continue
            proc = Procurement(
                procurement_number=lot,
                title=meta['title'],
                subject=meta['subject'],
                okpd2_code=code,
                okpd2_name=product,
                region=_customer_region(meta['customer_kpp']),
                initial_price=meta['start_price'],
                keywords=product,
                customer_inn=meta['customer_inn'],
                customer_kpp=meta['customer_kpp'],
                source_system=meta['source_system'],
                is_smp=meta['is_smp'],
                publish_date=_date(meta['publish_date']),
            )
            proc.procurement_kind = procurement_kind(proc)
            db.session.add(proc)
            if proc_idx % 500 == 0:
                db.session.flush()
                print(f'      исторические закупки: {proc_idx:,} / {len(chosen_lots):,}', flush=True)
        if chosen_lots:
            print(f'      исторические закупки: {len(chosen_lots):,} / {len(chosen_lots):,}', flush=True)

        for row in preserved_users:
            if not User.query.filter_by(email=row['email']).first():
                db.session.add(User(**row))

        db.session.commit()
        ensure_admin_user()
        print(f'    БД готова: {Supplier.query.count():,} поставщиков, '
              f'{SupplierContract.query.count():,} исторических побед, '
              f'{Procurement.query.count():,} закупок.')
        print('    Следующий шаг: scripts/enrich_gisp.py и импорт ОКВЭД/МСП.')


def choose_procurements(lot_meta, lot_tru, limit: int) -> list[str]:
    # Сначала обеспечиваем покрытие заказчиков: по одному свежему лоту на ИНН.
    themes = ['медицинск', 'питани', 'строит', 'связ', 'ремонт', 'оборудован']
    picked, seen = [], set()
    items = [(lot, meta) for lot, meta in lot_meta.items() if lot in lot_tru and lot_tru[lot][0]]
    items.sort(key=lambda x: x[1]['publish_date'], reverse=True)

    seen_customers = set()
    for lot, meta in items:
        customer = meta.get('customer_inn') or ''
        if customer and customer not in seen_customers:
            picked.append(lot); seen.add(lot); seen_customers.add(customer)
            if len(picked) >= limit:
                return picked

    # Затем добавляем тематически разнообразные примеры для live-demo.
    for theme in themes:
        n = 0
        for lot, meta in items:
            if lot in seen:
                continue
            text = (meta['title'] + ' ' + meta['subject']).lower()
            if theme in text:
                picked.append(lot); seen.add(lot); n += 1
                if len(picked) >= limit:
                    return picked
                if n >= 120:
                    break

    for lot, _ in items:
        if len(picked) >= limit:
            break
        if lot not in seen:
            picked.append(lot); seen.add(lot)
    return picked[:limit]


def _clean(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ''
    s = str(v).strip()
    return '' if s.lower() == 'nan' else s


def _float(v) -> float:
    try: return float(v)
    except (TypeError, ValueError): return 0.0


def _year(s: str) -> int:
    try: return int(str(s)[:4])
    except ValueError: return 2025


def _date(s: str):
    try: return datetime.strptime(str(s)[:10], '%Y-%m-%d').date()
    except ValueError: return None


def _customer_region(kpp: str) -> str:
    return LOCAL_PREFIX_TO_REGION.get((kpp or '')[:2], 'Санкт-Петербург')


if __name__ == '__main__':
    main()
