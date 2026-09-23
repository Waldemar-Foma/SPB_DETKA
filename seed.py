"""Наполняет базу демонстрационными данными.

Запуск: python seed.py

Генерация детерминированная: SEED фиксирует последовательность.
При каждом запуске получишь одинаковый набор компаний.

Координаты распределены по реальным районам Санкт-Петербурга и ЛО,
чтобы точки на карте были визуально разнесены.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

# Добавляем корень проекта в path, чтобы работал импорт app
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import create_app
from backend.extensions import db
from backend.models import Procurement, Supplier, SupplierContract

SEED = 42
TOTAL_SUPPLIERS = 40

# ==========================================================================
# СПРАВОЧНИКИ
# ==========================================================================

# --- Закупки --------------------------------------------------------------

PROCUREMENTS = [
    {
        "number": "2025-012345",
        "title": "Поставка медицинского оборудования",
        "okpd2_code": "32.50.50.190",
        "okpd2_name": "Медицинские инструменты и оборудование",
        "region": "Санкт-Петербург",
        "initial_price": 12_500_000,
        "keywords": "медицинское оборудование, инструменты, аппаратура",
    },
    {
        "number": "2025-045678",
        "title": "Поставка компьютерной техники",
        "okpd2_code": "26.20.11.000",
        "okpd2_name": "Компьютеры и периферийное оборудование",
        "region": "Санкт-Петербург",
        "initial_price": 8_300_000,
        "keywords": "компьютеры, ноутбуки, серверы, периферия",
    },
    {
        "number": "2025-077890",
        "title": "Ремонт дорожного покрытия",
        "okpd2_code": "42.11.20.000",
        "okpd2_name": "Работы дорожные",
        "region": "Ленинградская область",
        "initial_price": 45_000_000,
        "keywords": "ремонт дорог, асфальт, дорожное покрытие",
    },
    {
        "number": "2025-099112",
        "title": "Поставка продуктов питания",
        "okpd2_code": "10.89.11.000",
        "okpd2_name": "Продукты пищевые прочие",
        "region": "Санкт-Петербург",
        "initial_price": 5_600_000,
        "keywords": "продукты, питание, продовольствие",
    },
]

# --- Координаты по районам СПб и ЛО ---------------------------------------
# Каждая запись: (широта, долгота, название_района)
# Используются для реалистичного распределения точек на карте.

SPB_DISTRICTS = [
    (59.9420, 30.3150, "Центральный"),
    (59.9400, 30.2730, "Петроградский"),
    (59.9300, 30.3600, "Невский"),
    (59.8350, 30.1700, "Красносельский"),
    (59.8700, 30.4200, "Фрунзенский"),
    (59.9200, 30.4500, "Красногвардейский"),
    (59.9700, 30.2200, "Приморский"),
    (59.8900, 30.3000, "Московский"),
    (59.8800, 30.4800, "Обуховский"),
    (59.9600, 30.4000, "Калининский"),
    (59.9950, 30.3500, "Выборгский"),
    (59.8000, 30.1000, "Пушкинский"),
    (59.9300, 30.0100, "Петродворцовый"),
]

LO_DISTRICTS = [
    (59.5600, 30.1300, "Гатчина"),
    (60.7100, 28.7500, "Выборг"),
    (59.6400, 33.5500, "Тихвин"),
    (59.5300, 31.0000, "Кириши"),
    (60.0500, 30.3000, "Всеволожск"),
    (59.8500, 29.9000, "Ломоносов"),
    (60.9500, 29.1000, "Приозерск"),
]

OTHER_REGIONS = [
    ("Москва", 55.7558, 37.6173),
    ("Московская область", 55.9000, 37.8000),
    ("Новосибирская область", 55.0300, 82.9200),
    ("Республика Татарстан", 55.7900, 49.1200),
    ("Свердловская область", 56.8300, 60.6100),
]

# --- Названия -------------------------------------------------------------

NAME_ROOTS = [
    "МедТех", "ТехСнаб", "ПромМед", "БиоСнаб", "Медика", "ФармСервис",
    "ТехноМед", "МедКомплект", "СнабМед", "ПрофМедика", "АльфаМед",
    "МедОпт", "ТехГруп", "Медлайн", "СнабПро", "ТехноСервис", "БиоТех",
    "Медпоставка", "ПрофТех", "СнабТорг", "МедРесурс", "ТехАльянс",
    "КомпМед", "МедГарант", "ТехИмпорт", "МедТорг", "ПрофСнаб",
    "Медицинская техника", "ТехРезерв", "МедКомпани", "СмартМед",
    "ТехноПарк", "МедСтандарт", "ТехКонтакт", "БиоМед", "МедПроект",
    "ТехПром", "МедТендер", "ПромСнаб", "ТехМаркет",
]

NAME_SUFFIXES = ["", "-СПб", "-СЗФО", "-М", "-Плюс", "-Про", "Групп"]

LEGAL_FORMS = [("ООО", 70), ("АО", 15), ("ЗАО", 10), ("ИП", 5)]

COMPANY_TYPES = [
    ("Производитель", 30),
    ("Дистрибьютор", 40),
    ("Поставщик", 30),
]

# --- Опыт и выручка -------------------------------------------------------

EXPERIENCE_BUCKETS = [
    (1, 3, 25),
    (4, 7, 30),
    (8, 15, 30),
    (16, 25, 15),
]

REVENUE_BUCKETS = [
    (50_000_000,     300_000_000, 30),
    (300_000_000,    1_000_000_000, 35),
    (1_000_000_000,  3_000_000_000, 25),
    (3_000_000_000, 10_000_000_000, 10),
]

# --- ОКПД2 -----------------------------------------------------------------

OKPD2_CODES = [
    "32.50.50.190", "32.50.21.000", "32.50.13.110",
    "26.20.11.000", "26.20.15.000",
    "42.11.20.000",
    "10.89.11.000",
    "32.50.11.000", "26.20.21.000", "42.11.11.000", "10.89.19.000",
    "62.01.11.000", "71.12.12.000", "45.20.11.000", "49.41.11.000",
]

# --- Контракты -------------------------------------------------------------

CONTRACTS_PER_SUPPLIER = [
    (0, 0, 10),
    (1, 3, 20),
    (4, 9, 30),
    (10, 20, 25),
    (21, 40, 15),
]

CONTRACT_SUBJECTS = {
    "32.50.50.190": "Поставка медицинского оборудования",
    "26.20.11.000": "Поставка компьютерной техники",
    "42.11.20.000": "Работы по ремонту дорожного покрытия",
    "10.89.11.000": "Поставка продуктов питания",
    "DEFAULT": "Поставка товаров, выполнение работ",
}

# --- Улицы для адресов ----------------------------------------------------

STREETS_SPB = [
    "ул. Промышленная", "пр. Обуховской обороны", "ул. Салова",
    "Лиговский пр.", "ул. Кирочная", "наб. реки Фонтанки",
    "Московский пр.", "ул. Ленсовета", "Пулковское шоссе",
    "Большой пр. П.С.", "Невский пр.", "ул. Руставели",
]

STREETS_LO = [
    "Ленинградское шоссе", "пр. Ленина", "ул. Советская",
    "Красносельское шоссе", "ул. Гагарина",
]

STREETS_OTHER = [
    "ул. Ленина", "пр. Мира", "ул. Советская", "ул. Центральная",
    "ул. Гагарина", "ул. Победы",
]


# ==========================================================================
# ГЕНЕРАЦИЯ
# ==========================================================================

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
        print(f"\nГотово: {len(PROCUREMENTS)} закупок, "
              f"{len(suppliers)} контрагентов, "
              f"{SupplierContract.query.count()} контрактов.")


def _seed_procurements() -> None:
    for data in PROCUREMENTS:
        db.session.add(Procurement(
            procurement_number=data["number"],
            title=data["title"],
            okpd2_code=data["okpd2_code"],
            okpd2_name=data["okpd2_name"],
            region=data["region"],
            initial_price=data["initial_price"],
            keywords=data["keywords"],
        ))
    print(f"  закупок: {len(PROCUREMENTS)}")


def _seed_suppliers() -> list[Supplier]:
    suppliers: list[Supplier] = []
    used_inns: set[str] = set()

    for i in range(TOTAL_SUPPLIERS):
        data = _generate_supplier(i, used_inns)
        supplier = Supplier(**data)
        db.session.add(supplier)
        db.session.flush()
        suppliers.append(supplier)
        _seed_contracts(supplier, i)

    print(f"  контрагентов: {len(suppliers)}")
    return suppliers


def _generate_supplier(index: int, used_inns: set[str]) -> dict:
    legal_form = _weighted_choice(LEGAL_FORMS)
    root = NAME_ROOTS[index % len(NAME_ROOTS)]
    suffix = random.choice(NAME_SUFFIXES)
    name = f"{legal_form} «{root}{suffix}»"

    inn = _generate_unique_inn(used_inns)
    company_type = _weighted_choice(COMPANY_TYPES)
    years = _random_from_bucket(EXPERIENCE_BUCKETS)
    revenue = _random_from_bucket(REVENUE_BUCKETS)

    region, lat, lon = _pick_location(index)
    address = _generate_address(region, root)
    okpd2_codes = _pick_okpd2_codes()
    website, phone, email = _generate_contacts(used_inns, root)

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
        "is_verified": random.random() > 0.15,
        "revenue_annual": revenue,
        "okpd2_codes": ",".join(okpd2_codes),
        "lat": lat,
        "lon": lon,
    }


def _pick_location(index: int) -> tuple[str, float, float]:
    """Возвращает (регион, широта, долгота).

    Распределение:
      - 55% — Санкт-Петербург (13 районов, точки разнесены);
      - 20% — Ленинградская область (7 городов);
      - 25% — другие регионы.
    """
    r = random.random()

    if r < 0.55:
        lat, lon, _ = random.choice(SPB_DISTRICTS)
        # Небольшой шум, чтобы точки не накладывались
        lat += random.uniform(-0.008, 0.008)
        lon += random.uniform(-0.012, 0.012)
        return "Санкт-Петербург", round(lat, 5), round(lon, 5)

    if r < 0.75:
        lat, lon, _ = random.choice(LO_DISTRICTS)
        lat += random.uniform(-0.015, 0.015)
        lon += random.uniform(-0.020, 0.020)
        return "Ленинградская область", round(lat, 5), round(lon, 5)

    region, lat, lon = random.choice(OTHER_REGIONS)
    lat += random.uniform(-0.05, 0.05)
    lon += random.uniform(-0.05, 0.05)
    return region, round(lat, 5), round(lon, 5)


def _seed_contracts(supplier: Supplier, index: int) -> None:
    total = _random_from_bucket(CONTRACTS_PER_SUPPLIER)
    if total == 0:
        return

    primary_code = (supplier.okpd2_codes or "").split(",")[0]
    subject = CONTRACT_SUBJECTS.get(primary_code, CONTRACT_SUBJECTS["DEFAULT"])

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


# ==========================================================================
# ХЕЛПЕРЫ
# ==========================================================================

def _weighted_choice(pairs) -> str:
    items = list(pairs)
    values, weights = zip(*items)
    return random.choices(values, weights=weights, k=1)[0]


def _random_from_bucket(buckets) -> int:
    items = list(buckets)
    ranges = [(lo, hi) for lo, hi, _ in items]
    weights = [w for _, _, w in items]
    lo, hi = random.choices(ranges, weights=weights, k=1)[0]
    return random.randint(lo, hi)


def _generate_unique_inn(used: set[str]) -> str:
    while True:
        inn = random.choice("75") + "".join(random.choices("0123456789", k=9))
        if inn not in used:
            used.add(inn)
            return inn


def _pick_okpd2_codes() -> list[str]:
    count = random.choices([1, 2, 3], weights=[50, 35, 15], k=1)[0]
    return random.sample(OKPD2_CODES, k=count)


def _generate_contacts(used_inns: set[str], root: str):
    has_site = random.random() > 0.15
    has_phone = random.random() > 0.15
    has_email = random.random() > 0.20

    slug = root.lower().replace(" ", "-")[:20]
    domain = random.choice([".ru", ".spb.ru", ".com"])

    website = f"www.{slug}{domain}" if has_site else None
    phone = (f"+7 ({random.randint(800, 999)}) "
             f"{random.randint(100, 999)}-{random.randint(10, 99)}-"
             f"{random.randint(10, 99)}") if has_phone else None
    email = f"info@{slug}.ru" if has_email else None

    return website, phone, email


def _generate_address(region: str, root: str) -> str:
    if region == "Санкт-Петербург":
        street = random.choice(STREETS_SPB)
        return f"г. Санкт-Петербург, {street}, д. {random.randint(1, 120)}"
    if region == "Ленинградская область":
        street = random.choice(STREETS_LO)
        city = random.choice(["Гатчина", "Выборг", "Тихвин", "Кириши", "Всеволожск"])
        return f"Ленинградская обл., г. {city}, {street}, д. {random.randint(1, 80)}"
    street = random.choice(STREETS_OTHER)
    return f"{region}, {street}, д. {random.randint(1, 50)}"


if __name__ == "__main__":
    seed()
