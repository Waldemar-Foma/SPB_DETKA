"""Тесты для движка скоринга."""
from backend.services.matching_engine import compute_score, relevance_label


class _Proc:
    okpd2_code = "32.50.50.190"
    region = "Санкт-Петербург"
    initial_price = 12_500_000


class _Contract:
    def __init__(self, amount, year=2024):
        self.amount = amount
        self.year = year


class _Supplier:
    okpd2_codes = "32.50.50.190"
    name = "ООО «МедТех»"
    region = "Санкт-Петербург"
    revenue_annual = 2_400_000_000
    website = "medtech-spb.ru"
    phone = "+7 (812) 123-45-67"

    def __init__(self, contracts=None):
        self.contracts = contracts or []


def test_perfect_match_returns_high_score():
    supplier = _Supplier(contracts=[_Contract(1_000_000)] * 25)
    result = compute_score(_Proc(), supplier)
    assert result["total"] >= 90
    assert relevance_label(result["total"]) == "Высокая релевантность"


def test_no_okpd2_penalizes_score():
    supplier = _Supplier(contracts=[_Contract(1_000_000)] * 10)
    supplier.okpd2_codes = "11.11.11.111"
    result = compute_score(_Proc(), supplier)
    assert result["okpd2"] == 0


def test_region_mismatch_halves_region_score():
    supplier = _Supplier(contracts=[])
    supplier.region = "Москва"
    result = compute_score(_Proc(), supplier)
    assert result["region"] == 40