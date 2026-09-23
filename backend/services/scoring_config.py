"""Конфигурация скоринговой модели.

Все веса, пороги и бонусы собраны здесь, чтобы модель можно было
настраивать без правок в алгоритме. Веса читаются из переменных
окружения с дефолтами, что позволяет запускать разные пресеты
на демо (например, "жёсткий" и "мягкий" скоринг).
"""

from __future__ import annotations

import os


def _env_float(key: str, default: float) -> float:
    """Читает float из окружения, при ошибке возвращает default."""
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# --- Веса субиндексов (сумма = 1.0) --------------------------------------
# Значения по умолчанию соответствуют ТЗ. На хакатоне можно быстро
# перекосить модель в сторону, например, региона:
#   SPB_WEIGHT_REGION=0.40 SPB_WEIGHT_SCALE=0.05 python app.py
WEIGHTS = {
    "okpd2":      _env_float("SPB_WEIGHT_OKPD2",      0.30),
    "product":    _env_float("SPB_WEIGHT_PRODUCT",    0.25),
    "experience": _env_float("SPB_WEIGHT_EXPERIENCE", 0.20),
    "region":     _env_float("SPB_WEIGHT_REGION",     0.15),
    "scale":      _env_float("SPB_WEIGHT_SCALE",      0.10),
}

# --- Шкала интерпретации итогового балла ---------------------------------
RELEVANCE_THRESHOLDS = [
    (90, "Высокая релевантность"),
    (70, "Хорошая релевантность"),
    (50, "Средняя релевантность"),
    (0,  "Низкая релевантность"),
]

# --- Пороги для субиндексов ----------------------------------------------
# Собраны в один dict, чтобы логика читалась как «если count >= X, то Y».

# Опыт: сколько контрактов → сколько баллов
EXPERIENCE_STEPS = [
    (20, 94),
    (10, 75),
    (5,  55),
    (1,  30),
    (0,   0),
]

# Масштаб: отношение выручки к НМЦК → сколько баллов
SCALE_STEPS = [
    (10.0, 100),
    (5.0,   87),
    (2.0,   70),
    (1.0,   55),
    (0.0,   30),
]

# Регион: совпадает / не совпадает
REGION_MATCH_SCORE = 100
REGION_MISMATCH_SCORE = 40

# ОКПД2: точное / по классу / нет
OKPD2_EXACT_SCORE = 100
OKPD2_CLASS_SCORE = 70
OKPD2_NONE_SCORE = 0

# Fallback, если у компании нет данных по выручке
SCALE_FALLBACK_SCORE = 50