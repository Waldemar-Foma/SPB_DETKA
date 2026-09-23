"""Наполняет базу демонстрационными данными.

Генерация детерминированная: random.seed(42) фиксирует последовательность.
При каждом запуске получишь одинаковые 40 компаний и 4 закупки.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import create_app
from backend.extensions import db
from backend.models import Procurement, Supplier, SupplierContract
from backend.services import seed_data as sd

SEED = 42
TOTAL_SUPPLIERS = 40


def seed() -> None:
    """Пересоздаёт схему и заливает демо-данные."""
    random.seed(SEED)

    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        _seed_procurements()
        suppliers = _seed_suppliers()

        db.session.commit()
        print(f"\nГотово: {len(sd.PROCUREMENTS)} закупок, "
              f"{len(suppliers)} контрагентов, "
              f"{SupplierContract.query.count()} контрактов.")


def _seed_procurements() -> None:
    """Заливает 4 закупки из справочника."""
    for data in sd.PROCUREMENTS:
        db.session.add(Procurement(
            procurement_number=data["number"],
            title=data["title"],
            okpd2_code=data["okpd2_code"],
            okpd2_name=data["okpd2_name"],
            region=data["region"],
            initial_price=data["initial_price"],
            keywords=data["keywords"],
        ))
    print(f"  закупок: {len(sd.PROCUREMENTS)}")


def _seed_suppliers() -> list[Supplier]:
    """Генерирует TOTAL_SUPPLIERS компаний и контракты к ним."""
    suppliers: list[Supplier] = []
    used_inns: set[str] = set()

    for i in range(TOTAL_SUPPLIERS):
        data = _generate_supplier(i, used_inns)
        supplier = Supplier(**data)
        db.session.add(supplier)
        db.session.flush()  # чтобы получить supplier.id
        suppliers.append(supplier)

        _seed_contracts(supplier, i)

    print(f"  контрагентов: {len(suppliers)}")
    return suppliers


def _generate_supplier(index: int, used_inns: set[str]) -> dict:
    """Собирает словарь с полями одной компании."""
    legal_form = _weighted_choice(sd.LEGAL_FORMS)
    root = sd.NAME_ROOTS[index % len(sd.NAME_ROOTS)]
    suffix = random.choice(sd.NAME_SUFFIXES)
    name = f"{legal_form} «{root}{suffix}»"

    inn = _generate_unique_inn(used_inns)
    region = _weighted_choice(sd.REGIONS)
    company_type = _weighted_choice(sd.COMPANY_TYPES)
    years = _random_from_bucket(sd.EXPERIENCE_BUCKETS)
    revenue = _random_from_bucket(sd.REVENUE_BUCKETS)

    okpd2_codes = _pick_okpd2_codes()
    website, phone, email = _generate_contacts(index, used_inns, root)
    address = _generate_address(region, index)
    lat, lon = _generate_coords(region)

    return {
        "inn": inn,
        "ogrn": "1" + inn[:10] + "01",
        "name": name,
        "company_type": company_type,
        "region": region,
        "address": address,
        "website": website,
        "phone": phone,
        "email": email,
        "years_on_market": years,
        "is_verified": random.random() > 0.15,  # 15% без галочки
        "revenue_annual": revenue,
        "okpd2_codes": ",".join(okpd2_codes),
        "lat": lat,
        "lon": lon,
    }


def _seed_contracts(supplier: Supplier, index: int) -> None:
    """Добавляет компании N контрактов по годам."""
    total = _random_from_bucket(sd.CONTRACTS_PER_SUPPLIER)
    if total == 0:
        return

    # Основной ОКПД2 компании определяет тему контрактов.
    primary_code = (supplier.okpd2_codes or "").split(",")[0]
    subject = sd.CONTRACT_SUBJECTS.get(
        primary_code, sd.CONTRACT_SUBJECTS["DEFAULT"]
    )

    # Размазываем контракты по годам 2021–2025.
    years_pool = [2021, 2022, 2023, 2024, 2025]
    avg_amount = (float(supplier.revenue_annual or 0) or 100_000_000) * 0.05

    for n in range(total):
        year = random.choice(years_pool)
        amount = round(random.uniform(avg_amount * 0.4, avg_amount * 1.6), 2)
        db.session.add(SupplierContract(
            supplier_id=supplier.id,
            contract_number=f"{year}-{index:03d}-{n:03d}",
            year=year,
            amount=amount,
            subject=subject,
        ))


# --- Хелперы --------------------------------------------------------------

def _weighted_choice(pairs: Iterable[tuple[str, int]]) -> str:
    """Выбирает значение с учётом веса."""
    items = list(pairs)
    values, weights = zip(*items)
    return random.choices(values, weights=weights, k=1)[0]


def _random_from_bucket(buckets: Iterable[tuple[int, int, int]]) -> int:
    """Возвращает случайное число из выбранного весового диапазона."""
    items = list(buckets)
    ranges = [(lo, hi) for lo, hi, _ in items]
    weights = [w for _, _, w in items]
    lo, hi = random.choices(ranges, weights=weights, k=1)[0]
    return random.randint(lo, hi)


def _generate_unique_inn(used: set[str]) -> str:
    """Генерирует уникальный 10-значный ИНН.

    Формат совпадает с реальным: 10 цифр, начинается с 7 или 5.
    """
    while True:
        inn = random.choice("75") + "".join(random.choices("0123456789", k=9))
        if inn not in used:
            used.add(inn)
            return inn


def _pick_okpd2_codes() -> list[str]:
    """Подбирает 1–3 кода ОКПД2 для компании.

    С вероятностью 70% — из «профильных» (совпадение по классу),
    30% — из «чужих» (несовпадение), чтобы в ленте было разнообразие.
    """
    count = random.choices([1, 2, 3], weights=[50, 35, 15], k=1)[0]
    return random.sample(sd.OKPD2_CODES, k=count)


def _generate_contacts(index: int, used_inns: set[str], root: str) -> tuple[str | None, str | None, str | None]:
    """Возвращает (website, phone, email).

    У ~15% компаний часть контактов отсутствует — это нужно,
    чтобы фронт корректно обрабатывал неполные данные.
    """
    has_site = random.random() > 0.15
    has_phone = random.random() > 0.15
    has_email = random.random() > 0.20

    slug = root.lower().replace(" ", "-")[:20]
    inn = list(used_inns)[-1] if used_inns else "0000000000"

    website = f"www.{slug}{random.choice(sd.WEBSITE_DOMAINS)}" if has_site else None
    phone = (f"+7 ({random.randint(800, 999)}) "
             f"{random.randint(100, 999)}-{random.randint(10, 99)}-"
             f"{random.randint(10, 99)}") if has_phone else None
    email = f"info@{slug}.ru" if has_email else None

    return website, phone, email


def _generate_address(region: str, index: int) -> str:
    """Собирает адрес в зависимости от региона."""
    if region == "Санкт-Петербург":
        street = random.choice(sd.STREETS_SPB)
        return f"г. Санкт-Петербург, {street}, д. {random.randint(1, 120)}"
    if region == "Ленинградская область":
        return f"Ленинградская обл., г. {random.choice(['Гатчина', 'Выборг', 'Тихвин'])}, "
    if region == "Москва":
        street = random.choice(sd.STREETS_OTHER)
        return f"г. Москва, {street}, д. {random.randint(1, 80)}"
    street = random.choice(sd.STREETS_OTHER)
    return f"{region}, {street}, д. {random.randint(1, 50)}"


def _generate_coords(region: str) -> tuple[float, float]:
    """Случайные координаты в окрестностях центра региона."""
    centers = {
        "Санкт-Петербург": (59.93, 30.33),
        "Ленинградская область": (59.90, 30.60),
        "Москва": (55.75, 37.62),
        "Московская область": (55.75, 37.80),
        "Новосибирская область": (55.03, 82.92),
        "Республика Татарстан": (55.79, 49.12),
        "Свердловская область": (56.83, 60.61),
    }
    lat0, lon0 = centers.get(region, (59.93, 30.33))
    return (
        round(lat0 + random.uniform(-0.05, 0.05), 5),
        round(lon0 + random.uniform(-0.08, 0.08), 5),
    )


if __name__ == "__main__":
    seed()