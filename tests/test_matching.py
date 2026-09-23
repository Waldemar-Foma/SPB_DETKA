"""Тесты интеграции движка скоринга.

Проверяют, что compute_score() корректно собирает все пять
субиндексов и что итоговый балл попадает в ожидаемые диапазоны.
"""

from __future__ import annotations

from backend.services import scoring_config as cfg
from backend.services.matching_engine import compute_score, relevance_label


# --- Заглушки моделей -----------------------------------------------------
# Лёгкие объекты без SQLAlchemy: содержат ровно те атрибуты,
# к которым обращаются субиндексы. Это позволяет тестировать
# чистые функции без поднятия базы.

class _Contract:
    def __init__(self, amount: float = 1_000_000, year: int = 2024):
        self.amount = amount
        self.year = year


class _Proc:
    """Заглушка закупки. Включает keywords, который нужен product_score."""
    okpd2_code = "32.50.50.190"
    okpd2_name = "Медицинские инструменты и оборудование"
    region = "Санкт-Петербург"
    initial_price = 12_500_000
    keywords = "медицинское оборудование, инструменты, аппаратура"
    title = "Поставка медицинского оборудования"


class _Supplier:
    """Заглушка контрагента."""
    def __init__(
        self,
        okpd2_codes: str = "32.50.50.190",
        name: str = "ООО «МедТех»",
        company_type: str = "Производитель",
        region: str = "Санкт-Петербург",
        revenue: float | None = 2_400_000_000,
        contracts: list | None = None,
        website: str | None = "medtech-spb.ru",
        phone: str | None = "+7 (812) 123-45-67",
        is_verified: bool = True,
    ):
        self.okpd2_codes = okpd2_codes
        self.name = name
        self.company_type = company_type
        self.region = region
        self.revenue_annual = revenue
        self.contracts = contracts or []
        self.website = website
        self.phone = phone
        self.is_verified = is_verified


# --- Тесты: субиндексы попадают в правильные пороги ----------------------

def test_okpd2_exact_match():
    result = compute_score(_Proc(), _Supplier(okpd2_codes="32.50.50.190"))
    assert result["okpd2"] == cfg.OKPD2_EXACT_SCORE


def test_okpd2_class_match():
    result = compute_score(_Proc(), _Supplier(okpd2_codes="32.50.11.000"))
    assert result["okpd2"] == cfg.OKPD2_CLASS_SCORE


def test_okpd2_no_match():
    result = compute_score(_Proc(), _Supplier(okpd2_codes="62.01.11.000"))
    assert result["okpd2"] == cfg.OKPD2_NONE_SCORE


def test_region_match():
    result = compute_score(_Proc(), _Supplier(region="Санкт-Петербург"))
    assert result["region"] == cfg.REGION_MATCH_SCORE


def test_region_mismatch():
    result = compute_score(_Proc(), _Supplier(region="Москва"))
    assert result["region"] == cfg.REGION_MISMATCH_SCORE


def test_experience_zero():
    result = compute_score(_Proc(), _Supplier(contracts=[]))
    assert result["experience"] == 0


def test_experience_high():
    contracts = [_Contract() for _ in range(25)]
    result = compute_score(_Proc(), _Supplier(contracts=contracts))
    assert result["experience"] == cfg.EXPERIENCE_STEPS[0][1]


def test_scale_missing_revenue_uses_fallback():
    result = compute_score(_Proc(), _Supplier(revenue=None))
    assert result["scale"] == cfg.SCALE_FALLBACK_SCORE


# --- Тесты: итоговый балл и его интерпретация -----------------------------

def test_perfect_match_returns_high_score():
    """Компания с полным совпадением по всем факторам получает >= 80.

    Порог 80 (а не 90), потому что product_score использует
    эвристику и редко даёт ровно 100. На хакатоне, когда
    подключится ML-модель через semantic.product_similarity(),
    этот тест можно поднять до >= 90.
    """
    contracts = [_Contract() for _ in range(25)]
    supplier = _Supplier(
        name="МедТех Медицинское оборудование",
        contracts=contracts,
    )
    result = compute_score(_Proc(), supplier)
    assert result["total"] >= 80
    assert relevance_label(result["total"]) in {
        "Высокая релевантность",
        "Хорошая релевантность",
    }


def test_poor_match_returns_low_score():
    """Компания без совпадений по ключевым факторам получает < 50."""
    supplier = _Supplier(
        okpd2_codes="62.01.11.000",
        name="ООО «Ромашка»",
        company_type="Поставщик",
        region="Новосибирская область",
        revenue=100_000,
        contracts=[],
        website=None,
        phone=None,
    )
    result = compute_score(_Proc(), supplier)
    assert result["total"] < 50
    assert relevance_label(result["total"]) == "Низкая релевантность"
