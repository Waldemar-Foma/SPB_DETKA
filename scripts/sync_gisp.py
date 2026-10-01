"""Единая синхронизация ГИСП для BAT-файла и админ-панели."""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.gisp_worker import download_registry  # noqa: E402

STATUS = ROOT / "instance" / "gisp_sync_status.json"
OUTPUT = ROOT / "data" / "registry.xlsx"


def write_status(status: str, message: str, **extra):
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "message": message,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        **extra,
    }
    if STATUS.exists():
        try:
            old = json.loads(STATUS.read_text(encoding="utf-8"))
            if old.get("started_at") and "started_at" not in payload:
                payload["started_at"] = old["started_at"]
        except (OSError, ValueError):
            pass
    STATUS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    started = datetime.now().isoformat(timespec="seconds")
    write_status("running", "Скачиваем реестр ГИСП…", started_at=started)
    print("=== ГИСП: скачивание ===", flush=True)
    try:
        ok = asyncio.run(download_registry(OUTPUT))
        if not ok:
            write_status("error", "Не удалось скачать реестр ГИСП. Старый файл не считается новой синхронизацией.")
            return 1

        write_status("running", "Файл скачан. Выполняем сопоставление ИНН с локальной БД…")
        print("=== ГИСП: обогащение БД ===", flush=True)
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "enrich_gisp.py"), "--file", str(OUTPUT)],
            cwd=str(ROOT),
            check=False,
        )
        if result.returncode != 0:
            write_status("error", f"Файл скачан, но обогащение БД завершилось с кодом {result.returncode}.")
            return result.returncode

        write_status("ok", "ГИСП синхронизирован и данные записаны в БД.", finished_at=datetime.now().isoformat(timespec="seconds"))
        print("=== ГИСП: готово ===", flush=True)
        return 0
    except Exception as exc:
        write_status("error", f"Ошибка синхронизации: {exc}")
        print(f"ГИСП: критическая ошибка: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
