"""Тесты HTTP-эндпоинтов."""

from __future__ import annotations

import pytest

from app import create_app
from backend.extensions import db
from backend.models import Procurement, Supplier


@pytest.fixture
def client():
    app = create_app("test")
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


@pytest.fixture
def seeded_client(client):
    with client.application.app_context():
        db.session.add(Procurement(
            procurement_number="TEST-001",
            title="Поставка медицинского оборудования",
            okpd2_code="32.50.50.190",
            okpd2_name="Медицинские инструменты",
            region="Санкт-Петербург",
            initial_price=10_000_000,
            keywords="медицина, оборудование",
        ))
        db.session.add(Supplier(
            inn="7801234567",
            name="ООО «МедТех»",
            company_type="Производитель",
            region="Санкт-Петербург",
            years_on_market=12,
            revenue_annual=2_000_000_000,
            okpd2_codes="32.50.50.190",
            is_verified=True,
        ))
        db.session.commit()
    return client


def test_analyze_not_found_on_empty_db(client):
    resp = client.post("/api/v1/procurement/analyze", json={"query": "x"})
    assert resp.status_code == 404


def test_analyze_finds_procurement(seeded_client):
    resp = seeded_client.post(
        "/api/v1/procurement/analyze",
        json={"query": "медицинское оборудование"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["procurement_id"] == "TEST-001"
    assert data["okpd2"] == "32.50.50.190"


def test_suppliers_list_returns_pagination(seeded_client):
    resp = seeded_client.get("/api/v1/procurement/TEST-001/suppliers?limit=10")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "items" in data and "meta" in data
    assert data["meta"]["limit"] == 10
    assert data["meta"]["total"] >= 1


def test_supplier_details_not_found(client):
    resp = client.get("/api/v1/suppliers/0000000000/details")
    assert resp.status_code == 404


def test_supplier_details_ok(seeded_client):
    resp = seeded_client.get("/api/v1/suppliers/7801234567/details")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["inn"] == "7801234567"
    assert "scoring_breakdown" in data


def test_analytics_not_implemented(client):
    resp = client.get("/api/v1/analytics/regions")
    assert resp.status_code == 501