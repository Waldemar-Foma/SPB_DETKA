"""Понятные и воспроизводимые коэффициенты ранжирования."""
from __future__ import annotations

WEIGHT_PROFILES = {
    "balanced": {
        "product": 0.30,
        "okpd2": 0.12,
        "experience": 0.15,
        "win_rate": 0.10,
        "customer": 0.08,
        "geography": 0.15,
        "reviews": 0.05,
        "workload": 0.05,
    }
}

RELEVANCE_THRESHOLDS = [
    (85, "Отлично подходит"),
    (70, "Хорошо подходит"),
    (50, "Можно рассмотреть"),
    (0, "Есть заметные ограничения"),
]

OKPD2_EXACT_SCORE = 100
OKPD2_GROUP_SCORE = 85
OKPD2_CLASS_SCORE = 65
OKPD2_NONE_SCORE = 0


def get_weights(profile: str | None = None) -> dict[str, float]:
    return WEIGHT_PROFILES["balanced"]
