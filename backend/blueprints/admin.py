from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from sqlalchemy import text
from flask import Blueprint, current_app, jsonify, render_template, request

from backend.extensions import db
from backend.models import Procurement, RegistrySync, Supplier, SupplierContract, User
from backend.services.auth import admin_required, current_user
from backend.services.local_ai import LLM_MODEL, LLM_URL
from backend.services.candidate_retrieval import status as candidate_status, search_text as candidate_search
from backend.services.dataset_switcher import active_dataset, inspect_datasets, switch_dataset

bp = Blueprint("admin", __name__, url_prefix="/admin")
ROOT = Path(__file__).resolve().parents[2]
STATUS_FILE = ROOT / "instance" / "gisp_sync_status.json"
LOG_FILE = ROOT / "instance" / "gisp_sync.log"
GISP_FILE = ROOT / "data" / "registry.xlsx"
ENRICH_STATUS_FILE = ROOT / "instance" / "company_enrichment_status.json"
ENRICH_LOG_FILE = ROOT / "instance" / "company_enrichment.log"
REAL_MARKER = ROOT / "instance" / "REAL_DATA_READY"
SPEED_HISTORY_FILE = ROOT / "instance" / "api_speed_tests.json"
SPEED_HISTORY_LIMIT = 10


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


def _read_json_status(path: Path, idle_message: str):
    if not path.exists():
        return {"status": "idle", "message": idle_message}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "unknown", "message": "Не удалось прочитать файл статуса."}


def _tail_file(path: Path, lines: int = 24):
    if not path.exists():
        return ""
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


def _quick_models():
    """Быстрая проверка только тех AI-компонентов, которые показываем администратору."""
    llm = {"ok": False, "model": LLM_MODEL, "url": LLM_URL, "service_ok": False, "model_loaded": False}

    llm_base = LLM_URL.rsplit("/v1/", 1)[0]
    try:
        r = requests.get(llm_base + "/api/tags", timeout=1.8)
        llm["service_ok"] = bool(r.ok)
        llm["http_status"] = r.status_code
        if r.ok:
            names = [m.get("name", "") for m in (r.json().get("models") or [])]
            loaded = any(LLM_MODEL in name or name in LLM_MODEL for name in names)
            llm["model_loaded"] = loaded
            llm["ok"] = loaded
            llm["available_models"] = names[:20]
            if not loaded:
                llm["error"] = f"Ollama отвечает, но модель {LLM_MODEL} не загружена"
    except (requests.RequestException, ValueError) as exc:
        llm["error"] = str(exc)

    candidate = candidate_status(live=True)
    candidate["ok"] = bool(candidate.get("index_ok") and candidate.get("ollama_ok") and candidate.get("model_loaded"))
    if not candidate["ok"] and not candidate.get("reason"):
        if not candidate.get("index_ok"):
            candidate["reason"] = "FAISS-индекс не найден или не загружен"
        elif not candidate.get("ollama_ok"):
            candidate["reason"] = "Ollama недоступна"
        elif not candidate.get("model_loaded"):
            candidate["reason"] = "all-minilm не загружена"
    return {"candidate_search": candidate, "llm": llm}


def _gisp_runtime_status():
    try:
        import playwright  # noqa: F401
    except Exception as exc:
        return {"ok": False, "message": f"Playwright не установлен: {exc}"}

    browser_root = os.getenv("PLAYWRIGHT_BROWSERS_PATH")
    if browser_root:
        root = Path(browser_root)
        browser_ok = root.exists() and any(root.glob("chromium-*"))
        if not browser_ok:
            return {"ok": False, "message": f"Chromium Playwright не найден в {browser_root}"}

    index_map = ROOT / "ml_artifacts" / "supplier_index_map.csv"
    if not index_map.exists():
        return {"ok": False, "message": "Не найден supplier_index_map.csv для fallback-проверки ИНН"}

    return {
        "ok": True,
        "message": "готов · официальный ГИСП + fallback по публичному зеркалу",
        "official_source": "gisp.gov.ru",
        "fallback_source": "tovarminpro.online",
    }


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
        dataset_state=active_dataset(),
        datasets=inspect_datasets(),
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
            "active_dataset": active_dataset(),
            "datasets": inspect_datasets(),
        },
        "models": _quick_models(),
        "gisp": {
            "latest_sync": _latest_sync(),
            "file": _file_info(GISP_FILE),
            "job": _read_job_status(),
            "parser": _gisp_runtime_status(),
            "log_tail": _tail_log(),
        },
        "company_enrichment": {
            "job": _read_json_status(ENRICH_STATUS_FILE, "Обогащение тестовыми данными ещё не запускалось."),
            "log_tail": _tail_file(ENRICH_LOG_FILE, 28),
            "dadata_configured": bool((os.getenv("DADATA_TOKEN") or "").strip()),
            "test_data_url": os.getenv("YANDEX_TEST_DATA_URL", "Yandex Disk / Тестовые данные_1140"),
        },
    })


@bp.post("/api/dataset/<int:dataset_id>/activate")
@admin_required
def activate_dataset(dataset_id: int):
    try:
        state = switch_dataset(dataset_id)
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Dataset switch failed")
        return jsonify({"ok": False, "message": f"Не удалось переключить датасет: {exc}"}), 500

    return jsonify({
        "ok": True,
        "message": f"Датасет {dataset_id} активирован: {state['inserted']} закупок, {state.get('suppliers', {}).get('unique_suppliers', 0)} контрагентов.",
        "dataset": state,
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
    if not GISP_FILE.exists() or GISP_FILE.stat().st_size < 2_000:
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
            cwd=str(ROOT), capture_output=True, text=True, timeout=900, check=False,
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
        final = {"status": "error", "message": "Обогащение registry.xlsx превысило 15 минут."}
        STATUS_FILE.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
        return jsonify({"ok": False, "message": final["message"]}), 504


@bp.post("/api/enrichment/start")
@admin_required
def start_company_enrichment():
    current = _read_json_status(ENRICH_STATUS_FILE, "idle")
    if current.get("status") == "running":
        started = current.get("started_at")
        try:
            age = time.time() - datetime.fromisoformat(started).timestamp() if started else 0
        except (ValueError, TypeError):
            age = 0
        if age < 3600:
            return jsonify({"ok": False, "message": "Обогащение компаний уже выполняется", "job": current}), 409

    ENRICH_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENRICH_STATUS_FILE.write_text(json.dumps({
        "status": "running",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "message": "Запуск загрузки тестовых данных и DaData…",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    log = open(ENRICH_LOG_FILE, "a", encoding="utf-8")
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "sync_company_enrichment.py")],
        cwd=str(ROOT),
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
        close_fds=(os.name != "nt"),
    )
    log.close()
    return jsonify({"ok": True, "message": "Обогащение компаний запущено в фоне."}), 202


def _probe_candidate_search() -> dict:
    started = time.perf_counter()
    candidate = candidate_search("поставка серверного и сетевого оборудования", top_k=3)
    return {
        "ok": bool(candidate.get("ok") and candidate.get("items")),
        "engine": candidate.get("engine"),
        "model": candidate.get("model"),
        "indexed_suppliers": candidate.get("indexed_suppliers"),
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "sample": candidate.get("items", [])[:3],
        "error": candidate.get("reason"),
    }


def _probe_llm() -> dict:
    started = time.perf_counter()
    try:
        r = requests.post(
            LLM_URL,
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": "Ответь строго по-русски одним словом: готово."},
                    {"role": "user", "content": "Проверка локальной модели."},
                ],
                "temperature": 0,
                "max_tokens": 12,
                "stream": False,
            },
            timeout=15,
        )
        payload = r.json() if r.ok else {}
        text = (((payload.get("choices") or [{}])[0]).get("message") or {}).get("content") or ""
        return {
            "ok": bool(r.ok and text.strip()),
            "sample": text.strip()[:120],
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "http_status": r.status_code,
        }
    except (requests.RequestException, ValueError) as exc:
        return {"ok": False, "error": str(exc), "latency_ms": round((time.perf_counter() - started) * 1000)}


@bp.post("/api/models/test")
@admin_required
def test_models():
    return jsonify({"candidate_search": _probe_candidate_search(), "llm": _probe_llm()})


# ---------------------------------------------------------------------------
# Тесты API: замер скорости работы
# ---------------------------------------------------------------------------

# Только безопасные read-only запросы: тест ничего не меняет в данных.
HTTP_CHECKS = [
    {"id": "suppliers-list", "group": "Контрагенты", "label": "Реестр контрагентов", "path": "/api/v1/suppliers/"},
    {"id": "suppliers-registry", "group": "Контрагенты", "label": "Статус реестра", "path": "/api/v1/suppliers/registry-status"},
    {"id": "analytics-regions", "group": "Аналитика", "label": "Распределение по регионам", "path": "/api/v1/analytics/regions"},
    {"id": "analytics-types", "group": "Аналитика", "label": "Типы компаний", "path": "/api/v1/analytics/company-types"},
    {"id": "analytics-revenue", "group": "Аналитика", "label": "Группы по выручке", "path": "/api/v1/analytics/revenue-buckets"},
    {"id": "analytics-top", "group": "Аналитика", "label": "Топ по контрактам", "path": "/api/v1/analytics/top-contracts"},
    {"id": "procurement-list", "group": "Заявки", "label": "Список заявок", "path": "/api/v1/procurement/list"},
    {"id": "ai-status", "group": "ИИ", "label": "Статус локального ИИ", "path": "/api/v1/ai/status"},
    {"id": "admin-status", "group": "Админ-панель", "label": "Статус системы", "path": "/admin/api/status"},
]
AI_CHECK_IDS = ("ai-faiss", "ai-qwen")
SLOW_MS = 800
FAST_MS = 250


def _rating(avg_ms: float, ok: bool) -> str:
    if not ok:
        return "error"
    if avg_ms <= FAST_MS:
        return "fast"
    if avg_ms <= SLOW_MS:
        return "ok"
    return "slow"


def _measure(fn, runs: int) -> dict:
    """Запускает fn() runs раз и возвращает min/avg/max в мс и итог последнего вызова."""
    samples: list[float] = []
    outcome: dict = {"ok": False}
    for _ in range(runs):
        started = time.perf_counter()
        try:
            outcome = fn()
        except Exception as exc:  # noqa: BLE001 — тест не должен падать из-за одного эндпоинта
            outcome = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        samples.append((time.perf_counter() - started) * 1000)
        if not outcome.get("ok"):
            break  # нет смысла повторять сломанный запрос
    avg = sum(samples) / len(samples)
    return {
        **outcome,
        "runs": len(samples),
        "min_ms": round(min(samples), 1),
        "avg_ms": round(avg, 1),
        "max_ms": round(max(samples), 1),
        "rating": _rating(avg, bool(outcome.get("ok"))),
    }


def _http_check(client, path: str) -> dict:
    response = client.get(path)
    ok = 200 <= response.status_code < 300
    return {"ok": ok, "status": response.status_code, "error": None if ok else f"HTTP {response.status_code}"}


def _db_check() -> dict:
    db.session.execute(text("SELECT 1")).scalar()
    return {"ok": True, "status": None}


def _read_speed_history() -> list[dict]:
    if not SPEED_HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(SPEED_HISTORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _write_speed_history(entry: dict) -> list[dict]:
    history = ([entry] + _read_speed_history())[:SPEED_HISTORY_LIMIT]
    try:
        SPEED_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        SPEED_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass  # история — удобство, а не обязательное условие
    return history


@bp.get("/api-tests")
@admin_required
def api_tests_page():
    return render_template(
        "pages/admin_api_tests.html",
        page_id="admin-api-tests",
        page_title="Тесты АПИ",
        thresholds={"fast": FAST_MS, "slow": SLOW_MS},
        checks_total=len(HTTP_CHECKS) + 1,
    )


@bp.get("/api/speed-test/history")
@admin_required
def speed_test_history():
    history = _read_speed_history()
    return jsonify({"latest": history[0] if history else None, "history": history})


@bp.post("/api/speed-test")
@admin_required
def speed_test():
    body = request.get_json(silent=True) or {}
    try:
        runs = max(1, min(10, int(body.get("runs", 3))))
    except (TypeError, ValueError):
        runs = 3
    include_ai = bool(body.get("include_ai"))

    user = current_user()
    client = current_app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["user_email"] = (user.email or "").strip().lower()

    started_at = datetime.now()
    wall = time.perf_counter()
    results: list[dict] = []

    results.append({"id": "db-ping", "group": "База данных", "label": "Ping БД (SELECT 1)", "method": "SQL", "path": "SELECT 1",
                    **_measure(_db_check, runs)})
    for check in HTTP_CHECKS:
        results.append({**check, "method": "GET", **_measure(lambda p=check["path"]: _http_check(client, p), runs)})

    if include_ai:
        # ИИ-проверки тяжёлые, поэтому выполняются один раз и только по запросу.
        for check_id, group, label, probe in (
            ("ai-faiss", "ИИ", "Поиск кандидатов FAISS / all-minilm", _probe_candidate_search),
            ("ai-qwen", "ИИ", "Ответ локальной модели Qwen", _probe_llm),
        ):
            def run(probe=probe):
                result = probe()
                return {"ok": bool(result.get("ok")), "status": result.get("http_status"), "error": result.get("error")}
            results.append({"id": check_id, "group": group, "label": label, "method": "LOCAL", "path": "local-ai", **_measure(run, 1)})

    passed = [r for r in results if r["ok"]]
    timed = [r for r in passed if r["avg_ms"] is not None]
    slowest = max(timed, key=lambda r: r["avg_ms"]) if timed else None
    summary = {
        "checks": len(results),
        "passed": len(passed),
        "failed": len(results) - len(passed),
        "avg_ms": round(sum(r["avg_ms"] for r in timed) / len(timed), 1) if timed else None,
        "slowest": {"label": slowest["label"], "avg_ms": slowest["avg_ms"]} if slowest else None,
    }
    payload = {
        "ok": summary["failed"] == 0,
        "runs": runs,
        "include_ai": include_ai,
        "started_at": started_at.isoformat(timespec="seconds"),
        "total_ms": round((time.perf_counter() - wall) * 1000),
        "thresholds": {"fast": FAST_MS, "slow": SLOW_MS},
        "summary": summary,
        "results": results,
    }
    payload["history"] = _write_speed_history({k: payload[k] for k in ("started_at", "runs", "include_ai", "total_ms", "summary")})
    return jsonify(payload)
