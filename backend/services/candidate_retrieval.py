"""First-stage semantic retrieval from the supplied FAISS/all-minilm prototype.

The supplied model is intentionally used as a *candidate generator*, not as the
final decision maker. It returns semantically similar supplier INNs from the
prebuilt FAISS index; the main application then re-ranks these candidates with
OKPD2/history/win-rate/geography/reviews/workload and the customer's filters.

This preserves the useful part of the supplied prototype while avoiding two of
its documented limitations: FAISS similarity is not a probability and the
prototype index covers only 2,000 of the most active suppliers.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from threading import Lock
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = Path(os.getenv("CANDIDATE_ARTIFACT_DIR", ROOT / "ml_artifacts"))
INDEX_PATH = ARTIFACT_DIR / "suppliers.index"
MAP_PATH = ARTIFACT_DIR / "supplier_index_map.csv"
META_PATH = ARTIFACT_DIR / "index_meta.json"

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
EMBED_MODEL = os.getenv("CANDIDATE_EMBED_MODEL", "all-minilm")
EMBED_URL = f"{OLLAMA_BASE}/api/embed"
TIMEOUT = float(os.getenv("CANDIDATE_AI_TIMEOUT", "15"))
MAX_CHARS = int(os.getenv("CANDIDATE_MAX_CHARS", "400"))

_lock = Lock()
_index = None
_rows: list[dict[str, Any]] | None = None
_load_error: str | None = None


def procurement_query(procurement) -> str:
    """Build the text that the supplied retrieval model sees."""
    parts = [
        getattr(procurement, "title", "") or "",
        getattr(procurement, "subject", "") or "",
        getattr(procurement, "keywords", "") or "",
        getattr(procurement, "okpd2_name", "") or "",
    ]
    code = (getattr(procurement, "okpd2_code", "") or "").strip()
    if code and code.upper() != "AUTO":
        parts.append(f"ОКПД2 {code}")
    return " | ".join(p.strip() for p in parts if p and p.strip())[:MAX_CHARS]


def _load() -> tuple[Any, list[dict[str, Any]]]:
    global _index, _rows, _load_error
    if _index is not None and _rows is not None:
        return _index, _rows
    with _lock:
        if _index is not None and _rows is not None:
            return _index, _rows
        if not INDEX_PATH.exists():
            _load_error = f"FAISS index not found: {INDEX_PATH}"
            raise FileNotFoundError(_load_error)
        if not MAP_PATH.exists():
            _load_error = f"FAISS row map not found: {MAP_PATH}"
            raise FileNotFoundError(_load_error)
        try:
            import faiss  # lazy: app can still boot if optional ML deps are broken
        except Exception as exc:  # pragma: no cover - depends on runtime binary
            _load_error = f"faiss import failed: {exc}"
            raise RuntimeError(_load_error) from exc

        rows: list[dict[str, Any]] = []
        with MAP_PATH.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                rows.append(row)
        index = faiss.read_index(str(INDEX_PATH))
        if int(index.ntotal) != len(rows):
            _load_error = f"FAISS/map mismatch: index={index.ntotal}, map={len(rows)}"
            raise RuntimeError(_load_error)
        _index, _rows, _load_error = index, rows, None
        return _index, _rows


def _embed(text: str):
    """Embed query with the exact Ollama model used by the supplied index."""
    import numpy as np
    import faiss

    response = requests.post(
        EMBED_URL,
        json={"model": EMBED_MODEL, "input": [text[:MAX_CHARS]], "truncate": True},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    vectors = data.get("embeddings") or []
    if not vectors or not vectors[0]:
        raise RuntimeError("all-minilm returned an empty embedding")
    vector = np.asarray([vectors[0]], dtype="float32")
    faiss.normalize_L2(vector)
    return vector


def search_text(text: str, *, top_k: int = 80) -> dict[str, Any]:
    """Return first-stage candidates from the supplied model.

    Never raises to the web request: failures are reported in the returned
    status so the main application can transparently fall back to its DB
    prefilter.
    """
    clean = (text or "").strip()
    if not clean:
        return {"ok": False, "reason": "empty_query", "items": []}
    try:
        index, rows = _load()
        vector = _embed(clean)
        k = max(1, min(int(top_k), int(index.ntotal)))
        scores, indices = index.search(vector, k)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for rank, (idx, score) in enumerate(zip(indices[0], scores[0]), start=1):
            pos = int(idx)
            if pos < 0 or pos >= len(rows):
                continue
            row = rows[pos]
            inn = str(row.get("supplier_inn") or "").strip()
            if not inn or inn in seen:
                continue
            seen.add(inn)
            items.append({
                "inn": inn,
                "rank": rank,
                "similarity": float(score),
                "prototype_win_rate": _float(row.get("win_rate")),
                "prototype_wins": _int(row.get("total_wins")),
                "prototype_participations": _int(row.get("total_participations")),
                "prototype_role": str(row.get("estimated_role") or ""),
            })
        return {
            "ok": True,
            "engine": "all-minilm+faiss",
            "model": EMBED_MODEL,
            "indexed_suppliers": int(index.ntotal),
            "items": items,
        }
    except Exception as exc:
        return {
            "ok": False,
            "engine": "all-minilm+faiss",
            "model": EMBED_MODEL,
            "reason": str(exc),
            "items": [],
        }


def search_procurement(procurement, *, top_k: int = 80) -> dict[str, Any]:
    return search_text(procurement_query(procurement), top_k=top_k)


def status(*, live: bool = False) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    if META_PATH.exists():
        try:
            meta = json.loads(META_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
    result: dict[str, Any] = {
        "index_exists": INDEX_PATH.exists(),
        "map_exists": MAP_PATH.exists(),
        "model": EMBED_MODEL,
        "indexed_suppliers": meta.get("rows"),
        "dimensions": meta.get("dimensions"),
        "load_error": _load_error,
    }
    try:
        index, rows = _load()
        result.update({"index_ok": True, "indexed_suppliers": int(index.ntotal), "mapped_rows": len(rows)})
    except Exception as exc:
        result.update({"index_ok": False, "error": str(exc)})

    if live:
        try:
            r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=2)
            models = [str(m.get("name") or "") for m in ((r.json().get("models") or []) if r.ok else [])]
            result["ollama_ok"] = bool(r.ok)
            result["model_loaded"] = any(EMBED_MODEL in name for name in models)
            result["available_models"] = models[:20]
        except (requests.RequestException, ValueError) as exc:
            result["ollama_ok"] = False
            result["model_loaded"] = False
            result["ollama_error"] = str(exc)
    return result


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
