"""Локальные AI-клиенты системы подбора контрагентов.

Никаких внешних API нейросетей: оба сервиса ожидаются на localhost.
- multilingual-e5-base через llama-server /v1/embeddings
- qwen2.5:3b через Ollama OpenAI-compatible /v1/chat/completions

При недоступности моделей код возвращает None, а бизнес-логика использует
детерминированный fallback. Это важно для демонстрации: интерфейс не падает,
даже если один из локальных процессов ещё не поднят.
"""
from __future__ import annotations

import os
from collections import OrderedDict
import time
from typing import Any

import requests

EMBEDDINGS_URL = os.getenv(
    "LOCAL_EMBEDDINGS_URL", "http://127.0.0.1:8081/v1/embeddings"
)
EMBEDDINGS_MODEL = os.getenv("LOCAL_EMBEDDINGS_MODEL", "multilingual-e5-base")
LLM_URL = os.getenv(
    "LOCAL_LLM_URL", "http://127.0.0.1:11434/v1/chat/completions"
)
LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "qwen2.5:3b")
AI_TIMEOUT = float(os.getenv("LOCAL_AI_TIMEOUT", "8"))


def _post(url: str, payload: dict[str, Any], timeout: float | None = None) -> dict | None:
    try:
        response = requests.post(url, json=payload, timeout=timeout or AI_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        return None


_EMBED_CACHE: OrderedDict[str, tuple[float, ...]] = OrderedDict()
_EMBED_CACHE_MAX = 4096
_EMBED_FAILURE_UNTIL = 0.0


def embedding_many(texts: list[str], *, batch_size: int = 64) -> dict[str, tuple[float, ...] | None]:
    """Batch embeddings with cache support.

    llama-server accepts an array in the OpenAI-compatible ``input`` field.
    Warming candidate passages in batches is much faster than 200+ sequential
    HTTP calls during the top-5 calculation. Missing/failed vectors stay None
    and the scoring layer falls back to transparent lexical matching.
    """
    global _EMBED_FAILURE_UNTIL
    clean_texts = [str(t or "").strip() for t in texts]
    unique = list(dict.fromkeys(t for t in clean_texts if t))
    result: dict[str, tuple[float, ...] | None] = {}
    missing: list[str] = []

    for text in unique:
        cached = _EMBED_CACHE.get(text)
        if cached is not None:
            _EMBED_CACHE.move_to_end(text)
            result[text] = cached
        else:
            missing.append(text)

    if missing and time.monotonic() >= _EMBED_FAILURE_UNTIL:
        for start in range(0, len(missing), max(1, batch_size)):
            batch = missing[start:start + max(1, batch_size)]
            data = _post(
                EMBEDDINGS_URL,
                {"model": EMBEDDINGS_MODEL, "input": batch},
                timeout=max(AI_TIMEOUT, 15),
            )
            try:
                rows = data["data"]  # type: ignore[index]
                # Most OpenAI-compatible servers return rows with indexes.
                by_index = {int(row.get("index", idx)): row for idx, row in enumerate(rows)}
                for idx, text in enumerate(batch):
                    row = by_index.get(idx, rows[idx] if idx < len(rows) else {})
                    vector = tuple(float(x) for x in (row.get("embedding") or []))
                    if not vector:
                        raise ValueError("empty embedding")
                    _EMBED_CACHE[text] = vector
                    _EMBED_CACHE.move_to_end(text)
                    result[text] = vector
                while len(_EMBED_CACHE) > _EMBED_CACHE_MAX:
                    _EMBED_CACHE.popitem(last=False)
            except (TypeError, KeyError, IndexError, ValueError):
                _EMBED_FAILURE_UNTIL = time.monotonic() + 5.0
                for text in batch:
                    result.setdefault(text, None)
                # One broken batch is enough to switch the request to fallback.
                break
    else:
        for text in missing:
            result.setdefault(text, None)

    return {text: result.get(text) for text in clean_texts if text}


def embedding(text: str) -> tuple[float, ...] | None:
    """Возвращает embedding как tuple или None.

    Для multilingual-e5 сохраняем префикс query:/passage: снаружи — так один
    и тот же клиент можно использовать для обоих типов текста.
    """
    global _EMBED_FAILURE_UNTIL
    clean = (text or "").strip()
    if not clean:
        return None

    cached = _EMBED_CACHE.get(clean)
    if cached is not None:
        _EMBED_CACHE.move_to_end(clean)
        return cached

    # Circuit breaker: если llama-server выключен/завис, не ждём timeout для
    # каждой из десятков компаний. Через несколько секунд пробуем снова.
    if time.monotonic() < _EMBED_FAILURE_UNTIL:
        return None

    data = _post(
        EMBEDDINGS_URL,
        {"model": EMBEDDINGS_MODEL, "input": [clean]},
        timeout=AI_TIMEOUT,
    )
    try:
        vector = tuple(float(x) for x in data["data"][0]["embedding"])  # type: ignore[index]
        if not vector:
            raise ValueError("empty embedding")
        _EMBED_CACHE[clean] = vector
        _EMBED_CACHE.move_to_end(clean)
        while len(_EMBED_CACHE) > _EMBED_CACHE_MAX:
            _EMBED_CACHE.popitem(last=False)
        return vector
    except (TypeError, KeyError, IndexError, ValueError):
        _EMBED_FAILURE_UNTIL = time.monotonic() + 5.0
        return None


def chat(system: str, user: str, *, max_tokens: int = 120, temperature: float = 0.1) -> str | None:
    """Короткая локальная генерация через Ollama OpenAI-compatible API."""
    data = _post(
        LLM_URL,
        {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        },
        timeout=max(AI_TIMEOUT, 20),
    )
    try:
        text = data["choices"][0]["message"]["content"]  # type: ignore[index]
        return str(text).strip() or None
    except (TypeError, KeyError, IndexError):
        return None


def status() -> dict[str, bool]:
    """Быстрая проверка доступности обоих локальных компонентов."""
    emb = embedding("query: тест") is not None
    # Не генерируем полноценный ответ: endpoint может быть медленнее embeddings.
    try:
        base = LLM_URL.rsplit("/v1/", 1)[0]
        r = requests.get(base + "/api/tags", timeout=1.5)
        llm = r.ok
    except requests.RequestException:
        llm = False
    return {"embeddings": emb, "llm": llm}
