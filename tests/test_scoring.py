"""Тесты скоринговой модели: субиндексы и итоговый балл."""

from __future__ import annotations

import pytest

from backend.services import scoring_config as cfg
from backend.services.matching_engine import compute_score, relevance_label


# --- Заглушки моделей -----------------------------------------------------

class Contract:
    def __init__(self, amount: float = 1_000_000, year: int = 2024):
        self.amount = amount
        self.year = year


class Procurement:
    okpd2_code = "32.50.50.190"
    okpd2_name = "Медицинские инструменты и оборудование"
    region = "Санкт-Петербург"
    initial_price = 12_500_000
    keywords = "медицинское оборудование, инструменты"
    title = "Поставка медицинского оборудования"


class Supplier:
    def __init__(
        self,
        okpd2_codes: str = "32.50.50.190",
        name: str = "ООО «МедТех»",
        company_type: str = "Производитель",
        region: str = "Санкт-Петербург",
        revenue: float | None = 2_400_000_000,
        contracts: list | None = None,
        website: str | None = "medtech.ru",
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


# --- Тесты субиндексов ---------------------------------------------------

def test_okpd2_exact_match():
    result = compute_score(Procurement(), Supplier(okpd2_codes="32.50.50.190"))
    assert result["okpd2"] == cfg.OKPD2_EXACT_SCORE


def test_okpd2_class_match():
    result = compute_score(Procurement(), Supplier(okpd2_codes="32.50.11.000"))
    assert result["okpd2"] == cfg.OKPD2_CLASS_SCORE


def test_okpd2_no_match():
    result = compute_score(Procurement(), Supplier(okpd2_codes="62.01.11.000"))
    assert result["okpd2"] == cfg.OKPD2_NONE_SCORE


def test_region_mismatch():
    result = compute_score(Procurement(), Supplier(region="Москва"))
    assert result["region"] == cfg.REGION_MISMATCH_SCORE


def test_experience_zero():
    result = compute_score(Procurement(), Supplier(contracts=[]))
    assert result["experience"] == 0


def test_experience_high():
    contracts = [Contract() for _ in range(25)]
    result = compute_score(Procurement(), Supplier(contracts=contracts))
    assert result["experience"] == cfg.EXPERIENCE_STEPS[0][1]


def test_scale_missing_revenue_uses_fallback():
    result = compute_score(Procurement(), Supplier(revenue=None))
    assert result["scale"] == cfg.SCALE_FALLBACK_SCORE


# --- Тесты интеграции -----------------------------------------------------

def test_perfect_match_high_score():
    contracts = [Contract() for _ in range(25)]
    result = compute_score(Procurement(), Supplier(contracts=contracts))
    assert result["total"] >= 90
    assert relevance_label(result["total"]) == "Высокая релевантность"


def test_weights_sum_to_one():
    assert pytest.approx(sum(cfg.WEIGHTS.values()), rel=1e-6) == 1.0