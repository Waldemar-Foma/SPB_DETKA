"""Семантическое сопоставление продукции.

На хакатоне сюда подключается ML-модель (например,
sentence-transformers с paraphrase-multilingual-MiniLM-L12-v2).

Сейчас модуль возвращает None, чтобы product_score() использовал
эвристический fallback. Как только появится реальная модель,
достаточно реализовать _embed() и убрать заглушку в product_similarity().
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.models import Procurement, Supplier


# --- Публичный API --------------------------------------------------------

def product_similarity(procurement: "Procurement", supplier: "Supplier") -> float | None:
    """Возвращает косинусную близость 0..1 или None, если модель недоступна.

    None — сигнал вызывающему коду использовать fallback.
    """
    if not _is_model_available():
        return None

    text_a = _procurement_text(procurement)
    text_b = _supplier_text(supplier)
    vec_a, vec_b = _embed(text_a), _embed(text_b)

    if vec_a is None or vec_b is None:
        return None

    return _cosine(vec_a, vec_b)


# --- Точки расширения -----------------------------------------------------

def _is_model_available() -> bool:
    """Проверяет, подключена ли модель.

    На хакатоне: возвращает True, если sentence-transformers установлен
    и модель загружена. Сейчас — всегда False.
    """
    return False


@lru_cache(maxsize=1)
def _load_model():
    """Загружает модель один раз.

    Пример реализации для хакатона:

        from sentence_transformers import SentenceTransformer
        return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    """
    return None


@lru_cache(maxsize=512)
def _embed(text: str):
    """Возвращает вектор текста. Сейчас — None."""
    model = _load_model()
    if model is None:
        return None
    return model.encode(text, normalize_embeddings=True)


# --- Внутренние утилиты ---------------------------------------------------

def _procurement_text(procurement: "Procurement") -> str:
    """Собирает текстовое представление закупки для эмбеддинга."""
    parts = [
        procurement.title or "",
        procurement.okpd2_name or "",
        procurement.keywords or "",
    ]
    return " ".join(p for p in parts if p).strip()


def _supplier_text(supplier: "Supplier") -> str:
    """Собирает текстовое представление компании для эмбеддинга."""
    parts = [
        supplier.name or "",
        supplier.company_type or "",
    ]
    return " ".join(p for p in parts if p).strip()


def _cosine(a, b) -> float:
    """Косинусная близость двух нормализованных векторов."""
    try:
        import numpy as np
        return float(np.dot(a, b))
    except ImportError:
        # На случай отсутствия numpy — скалярное произведение вручную.
        return float(sum(x * y for x, y in zip(a, b)))