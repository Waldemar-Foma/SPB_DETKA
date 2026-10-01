from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from flask import Blueprint, jsonify, render_template

from backend.models import Procurement, RegistrySync, Supplier, SupplierContract, User
from backend.services.auth import admin_required
from backend.services.local_ai import EMBEDDINGS_MODEL, EMBEDDINGS_URL, LLM_MODEL, LLM_URL
from backend.services.candidate_retrieval import status as candidate_status, search_text as candidate_search

bp = Blueprint("admin", __name__, url_prefix="/admin")
ROOT = Path(__file__).resolve().parents[2]
STATUS_FILE = ROOT / "instance" / "gisp_sync_status.json"
LOG_FILE = ROOT / "instance" / "gisp_sync.log"
GISP_FILE = ROOT / "data" / "registry.xlsx"
REAL_MARKER = ROOT / "instance" / "REAL_DATA_READY"


def _latest_sync():
    sync = RegistrySync.query.order_by(RegistrySync.finished_at.desc()).first()
    if not sync:
        return None
    return {
        "source": sync.source,
        "status": sync.status,
        "rows_total": sync.rows_total,
        "matched_suppliers": sync.matched_suppliers,
        "message": sync.message,
        "finished_at": sync.finished_at.isoformat() if sync.finished_at else None,
    }


def _file_info(path: Path):
    if not path.exists():
        return {"exists": False, "path": str(path)}
    stat = path.stat()
    return {
        "exists": True,
        "path": str(path),
        "size_mb": round(stat.st_size / 1024 / 1024, 2),
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }


def _read_job_status():
    if not STATUS_FILE.exists():
        return {"status": "idle", "message": "Синхронизация из админ-панели ещё не запускалась."}
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "unknown", "message": "Не удалось прочитать файл статуса."}


def _tail_log(lines: int = 24):
    if not LOG_FILE.exists():
        return ""
    try:
        return "\n".join(LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


def _quick_models():
    embeddings = {"ok": False, "model": EMBEDDINGS_MODEL, "url": EMBEDDINGS_URL}
    llm = {"ok": False, "model": LLM_MODEL, "url": LLM_URL}

    emb_base = EMBEDDINGS_URL.rsplit("/v1/", 1)[0]
    try:
        r = requests.get(emb_base + "/health", timeout=1.2)
        if not r.ok:
            r = requests.get(emb_base + "/v1/models", timeout=1.2)
        embeddings["ok"] = bool(r.ok)
        embeddings["http_status"] = r.status_code
    except requests.RequestException as exc:
        embeddings["error"] = str(exc)

    llm_base = LLM_URL.rsplit("/v1/", 1)[0]
    try:
        r = requests.get(llm_base + "/api/tags", timeout=1.2)
        llm["ok"] = bool(r.ok)
        llm["http_status"] = r.status_code
        if r.ok:
            names = [m.get("name", "") for m in (r.json().get("models") or [])]
            llm["loaded"] = any(LLM_MODEL in name or name in LLM_MODEL for name in names)
            llm["available_models"] = names[:20]
    except (requests.RequestException, ValueError) as exc:
        llm["error"] = str(exc)

    candidate = candidate_status(live=True)
    candidate["ok"] = bool(candidate.get("index_ok") and candidate.get("ollama_ok") and candidate.get("model_loaded"))
    return {"candidate_search": candidate, "embeddings": embeddings, "llm": llm}


@bp.get("/")
@admin_required
def page():
    sources = [row[0] for row in Supplier.query.with_entities(Supplier.data_source).distinct().all() if row[0]]
    data_mode = "REAL" if REAL_MARKER.exists() or "hackathon_24_25" in sources else "DEMO"
    return render_template(
        "pages/admin.html",
        page_id="admin",
        page_title="Администрирование",
        counts={
            "suppliers": Supplier.query.count(),
            "procurements": Procurement.query.count(),
            "contracts": SupplierContract.query.count(),
            "users": User.query.count(),
        },
        data_sources=sources,
        data_mode=data_mode,
        latest_sync=_latest_sync(),
        gisp_file=_file_info(GISP_FILE),
    )


@bp.get("/api/status")
@admin_required
def status_api():
    return jsonify({
        "database": {
            "mode": "REAL" if REAL_MARKER.exists() or Supplier.query.filter_by(data_source="hackathon_24_25").first() else "DEMO",
            "sources": [row[0] for row in Supplier.query.with_entities(Supplier.data_source).distinct().all() if row[0]],
            "suppliers": Supplier.query.count(),
            "procurements": Procurement.query.count(),
            "contracts": SupplierContract.query.count(),
            "users": User.query.count(),
            "gisp_manufacturers": Supplier.query.filter_by(is_gisp_manufacturer=True).count(),
            "enriched_suppliers": Supplier.query.filter(Supplier.enrichment_updated_at.isnot(None)).count(),
        },
        "models": _quick_models(),
        "gisp": {
            "latest_sync": _latest_sync(),
            "file": _file_info(GISP_FILE),
            "job": _read_job_status(),
            "log_tail": _tail_log(),
        },
    })


@bp.post("/api/gisp/start")
@admin_required
def start_gisp():
    current = _read_job_status()
    if current.get("status") == "running":
        started = current.get("started_at")
        # Не создаём несколько параллельных браузеров. Старый stale-lock после 30 минут можно перезапустить.
        try:
            age = time.time() - datetime.fromisoformat(started).timestamp() if started else 0
        except (ValueError, TypeError):
            age = 0
        if age < 1800:
            return jsonify({"ok": False, "message": "Синхронизация уже выполняется", "job": current}), 409

    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    status = {
        "status": "running",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "message": "Запуск синхронизации ГИСП…",
    }
    STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    log = open(LOG_FILE, "a", encoding="utf-8")
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "sync_gisp.py")],
        cwd=str(ROOT),
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
        close_fds=(os.name != "nt"),
    )
    log.close()
    return jsonify({"ok": True, "message": "Синхронизация ГИСП запущена в фоне."}), 202


@bp.post("/api/gisp/enrich-existing")
@admin_required
def enrich_existing_gisp():
    """Повторно применяет уже скачанный registry.xlsx без обращения к сайту ГИСП."""
    if not GISP_FILE.exists() or GISP_FILE.stat().st_size < 10_000:
        return jsonify({"ok": False, "message": "data/registry.xlsx не найден или файл слишком мал"}), 400

    status = {
        "status": "running",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "message": "Применяем существующий registry.xlsx к локальной БД…",
    }
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "enrich_gisp.py"), "--file", str(GISP_FILE)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=180, check=False,
        )
        output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()[-4000:]
        final = {
            "status": "ok" if result.returncode == 0 else "error",
            "message": "Существующий registry.xlsx применён к БД." if result.returncode == 0 else f"Обогащение завершилось с кодом {result.returncode}.",
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }
        STATUS_FILE.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
        with LOG_FILE.open("a", encoding="utf-8") as log:
            log.write("\n=== Повторное применение registry.xlsx ===\n" + output + "\n")
        if result.returncode != 0:
            return jsonify({"ok": False, "message": final["message"], "output": output}), 500
        return jsonify({"ok": True, "message": final["message"], "output": output})
    except subprocess.TimeoutExpired:
        final = {"status": "error", "message": "Обогащение registry.xlsx превысило 180 секунд."}
        STATUS_FILE.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
        return jsonify({"ok": False, "message": final["message"]}), 504


@bp.post("/api/models/test")
@admin_required
def test_models():
    result = {"candidate_search": {"ok": False}, "embeddings": {"ok": False}, "llm": {"ok": False}}

    started = time.perf_counter()
    candidate = candidate_search("поставка серверного и сетевого оборудования", top_k=3)
    result["candidate_search"] = {
        "ok": bool(candidate.get("ok") and candidate.get("items")),
        "engine": candidate.get("engine"),
        "model": candidate.get("model"),
        "indexed_suppliers": candidate.get("indexed_suppliers"),
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "sample": candidate.get("items", [])[:3],
        "error": candidate.get("reason"),
    }

    started = time.perf_counter()
    try:
        r = requests.post(
            EMBEDDINGS_URL,
            json={"model": EMBEDDINGS_MODEL, "input": ["query: тест поставщика"]},
            timeout=4,
        )
        payload = r.json() if r.ok else {}
        vector = ((payload.get("data") or [{}])[0]).get("embedding") or []
        result["embeddings"] = {
            "ok": bool(r.ok and vector),
            "dimensions": len(vector),
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "http_status": r.status_code,
        }
    except (requests.RequestException, ValueError) as exc:
        result["embeddings"] = {"ok": False, "error": str(exc), "latency_ms": round((time.perf_counter() - started) * 1000)}

    started = time.perf_counter()
    try:
        r = requests.post(
            LLM_URL,
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": "Ответь одним словом: готово."},
                    {"role": "user", "content": "Проверка локальной модели."},
                ],
                "temperature": 0,
                "max_tokens": 8,
                "stream": False,
            },
            timeout=12,
        )
        payload = r.json() if r.ok else {}
        text = (((payload.get("choices") or [{}])[0]).get("message") or {}).get("content") or ""
        result["llm"] = {
            "ok": bool(r.ok and text.strip()),
            "sample": text.strip()[:120],
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "http_status": r.status_code,
        }
    except (requests.RequestException, ValueError) as exc:
        result["llm"] = {"ok": False, "error": str(exc), "latency_ms": round((time.perf_counter() - started) * 1000)}

    return jsonify(result)
