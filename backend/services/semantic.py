"""Семантическое сопоставление закупки и профиля контрагента.

Используется локальная multilingual-e5-base, поднятая через llama-server.
Если сервер недоступен, возвращается None и скоринг переходит на прозрачную
лексическую эвристику.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .local_ai import embedding, embedding_many

if TYPE_CHECKING:
    from backend.models import Procurement, Supplier


def product_similarity(procurement: "Procurement", supplier: "Supplier") -> float | None:
    query = "query: " + _procurement_text(procurement)
    passage = "passage: " + _supplier_text(supplier)
    a = embedding(query)
    b = embedding(passage)
    if a is None or b is None or len(a) != len(b):
        return None
    return _cosine(a, b)


def _procurement_text(procurement: "Procurement") -> str:
    parts = [
        procurement.title or "",
        procurement.okpd2_name or "",
        procurement.okpd2_code or "",
        procurement.keywords or "",
        getattr(procurement, "subject", "") or "",
    ]
    return " ".join(p for p in parts if p).strip()


def _supplier_text(supplier: "Supplier") -> str:
    parts = [
        supplier.name or "",
        getattr(supplier, "specialization", "") or "",
        supplier.okpd2_codes or "",
        getattr(supplier, "primary_okved", "") or "",
        supplier.company_type or "",
    ]
    return " ".join(p for p in parts if p).strip()


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if not na or not nb:
        return 0.0
    # E5 обычно выдаёт положительную близость, но жёстко ограничиваем диапазон.
    return max(0.0, min(1.0, dot / (na * nb)))


def warm_similarity_cache(procurement: "Procurement", suppliers: list["Supplier"]) -> None:
    """Pre-compute E5 vectors for the shortlist in a few batch requests."""
    query = "query: " + _procurement_text(procurement)
    passages = ["passage: " + _supplier_text(s) for s in suppliers]
    embedding_many([query, *passages], batch_size=64)
