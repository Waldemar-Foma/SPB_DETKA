"""Синхронизация статуса производителей по реестру ГИСП.

Основной источник — официальный публичный реестр ГИСП. На практике ГИСП
может отдавать 403 автоматизированным браузерам/контейнерам. Поэтому worker
не зависает на заблокированном endpoint: при явном 403 быстро переключается
на публичное зеркало реестра и проверяет ИНН компаний из FAISS-пула.

Зеркало используется только как fallback. В сгенерированном XLSX явно
записывается источник, а enrich_gisp.py трактует такую выгрузку как частичную:
она может добавить подтверждённых производителей, но не сбрасывает ранее
подтверждённые официальной полной выгрузкой статусы.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import requests
from openpyxl import Workbook
from playwright.async_api import BrowserContext, Page, async_playwright

ROOT = Path(__file__).resolve().parents[1]
HOSTS = (
    "https://portfolio.gisp.gov.ru",
    "https://gisp.gov.ru",
)
CATALOG_PATH = "/pp719v2/pub/prod/"
KNOWN_DOWNLOAD_PATHS = (
    "/pp719v2/mptapp/view/dl/production_res_valid_only/",
    "/pp719v2/mptapp/view/dl/production_res_valid_only.xlsx",
)
DOWNLOAD_TEXT = "Скачать только действующие"

# Публичное независимое зеркало сведений реестра. Используется только если
# официальный ГИСП блокирует автоматический доступ.
MIRROR_URL = os.getenv("GISP_MIRROR_URL", "https://tovarminpro.online/")
MIRROR_CACHE = ROOT / "data" / "gisp_mirror_cache.json"
OFFICIAL_BLOCK_CACHE = ROOT / "instance" / "gisp_official_block.json"
INDEX_MAP = ROOT / "ml_artifacts" / "supplier_index_map.csv"
CACHE_TTL_DAYS = int(os.getenv("GISP_MIRROR_CACHE_DAYS", "7"))
MIRROR_WORKERS = max(1, min(16, int(os.getenv("GISP_MIRROR_WORKERS", "10"))))
MIRROR_TIMEOUT = float(os.getenv("GISP_MIRROR_TIMEOUT", "8"))
OFFICIAL_BLOCK_HOURS = max(1, int(os.getenv("GISP_OFFICIAL_BLOCK_HOURS", "6")))


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data and data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.parts)).strip()


def _log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def _official_block_active() -> bool:
    if not OFFICIAL_BLOCK_CACHE.exists():
        return False
    try:
        payload = json.loads(OFFICIAL_BLOCK_CACHE.read_text(encoding="utf-8"))
        until = datetime.fromisoformat(payload.get("blocked_until", ""))
        return until > datetime.now()
    except (OSError, ValueError, TypeError):
        return False


def _remember_official_block() -> None:
    OFFICIAL_BLOCK_CACHE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "blocked_at": datetime.now().isoformat(timespec="seconds"),
        "blocked_until": (datetime.now() + timedelta(hours=OFFICIAL_BLOCK_HOURS)).isoformat(timespec="seconds"),
        "reason": "HTTP 403",
    }
    OFFICIAL_BLOCK_CACHE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _clear_official_block() -> None:
    try:
        OFFICIAL_BLOCK_CACHE.unlink(missing_ok=True)
    except OSError:
        pass


def _looks_like_xlsx(data: bytes) -> bool:
    if len(data) < 2_000 or data[:2] != b"PK":
        return False
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            names = set(zf.namelist())
            return "[Content_Types].xml" in names and any(name.startswith("xl/") for name in names)
    except (zipfile.BadZipFile, OSError):
        return False


def _commit_xlsx(data: bytes, output: Path) -> bool:
    if not _looks_like_xlsx(data):
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, output)
    _log(f"ГИСП: XLSX сохранён: {output} ({len(data) / 1024 / 1024:.1f} МБ)")
    return True


async def _request_download(context: BrowserContext, url: str) -> tuple[int | None, bytes | None]:
    try:
        response = await context.request.get(
            url,
            timeout=25_000,
            headers={
                "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/octet-stream,*/*",
                "Referer": url.rsplit("/pp719v2/", 1)[0] + CATALOG_PATH,
            },
        )
        body = await response.body()
        content_type = response.headers.get("content-type", "")
        _log(f"ГИСП: GET {url} → HTTP {response.status}, {len(body)} байт, {content_type or 'без content-type'}")
        return response.status, body if response.ok else None
    except Exception as exc:
        _log(f"ГИСП: request-context не смог скачать {url}: {exc}")
        return None, None


async def _discover_links(page: Page) -> list[str]:
    try:
        raw = await page.locator("a").evaluate_all(
            "els => els.map(a => ({text:(a.innerText||a.textContent||'').trim(), href:a.href||''}))"
        )
    except Exception:
        return []
    urls: list[str] = []
    for item in raw:
        text = str(item.get("text") or "").lower()
        href = str(item.get("href") or "")
        if href and ("только действующ" in text or "production_res_valid_only" in href.lower()):
            urls.append(href)
    return list(dict.fromkeys(urls))


async def _click_download(page: Page) -> bytes | None:
    selectors = [
        f'a:has-text("{DOWNLOAD_TEXT}")',
        f'button:has-text("{DOWNLOAD_TEXT}")',
        'a:has-text("действующие")',
        'button:has-text("действующие")',
    ]
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.count() == 0 or not await locator.is_visible(timeout=1_500):
                continue
            _log(f"ГИСП: пробуем UI download через {selector}")
            async with page.expect_download(timeout=25_000) as info:
                await locator.click(timeout=8_000)
            download = await info.value
            temp_path = await download.path()
            if temp_path:
                return Path(temp_path).read_bytes()
        except Exception as exc:
            _log(f"ГИСП: UI download не сработал: {exc}")
    return None


async def _try_official_host(browser, host: str) -> tuple[bytes | None, bool]:
    """Возвращает (xlsx, blocked_403). При 403 не тратим минуты на бесполезную navigation."""
    context = await browser.new_context(
        accept_downloads=True,
        ignore_https_errors=True,
        locale="ru-RU",
        viewport={"width": 1440, "height": 1000},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        extra_http_headers={"Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7", "Cache-Control": "no-cache"},
    )
    page = await context.new_page()
    catalog = host + CATALOG_PATH
    try:
        _log(f"ГИСП: открываем {catalog}")
        response = await page.goto(catalog, wait_until="domcontentloaded", timeout=25_000)
        status = response.status if response else None
        _log(f"ГИСП: страница реестра → HTTP {status or 'n/a'}, итоговый URL {page.url}")
        if status == 403:
            _log("ГИСП: официальный сайт блокирует автоматический доступ (403); переключаемся на fallback без долгих таймаутов.")
            return None, True
        if status and status >= 400:
            return None, False

        await page.wait_for_timeout(2_000)
        parsed = urlparse(page.url)
        origins = [f"{parsed.scheme}://{parsed.netloc}"] if parsed.scheme and parsed.netloc else []
        origins += [host]
        origins += list(HOSTS)
        origins = list(dict.fromkeys(origins))

        candidates = await _discover_links(page)
        for origin in origins:
            candidates.extend(origin + path for path in KNOWN_DOWNLOAD_PATHS)
        candidates = list(dict.fromkeys(candidates))

        blocked = False
        for url in candidates:
            request_status, body = await _request_download(context, url)
            blocked = blocked or request_status == 403
            if body and _looks_like_xlsx(body):
                return body, blocked

        body = await _click_download(page)
        if body and _looks_like_xlsx(body):
            return body, blocked

        return None, blocked
    except Exception as exc:
        _log(f"ГИСП: официальный host {host} недоступен: {exc}")
        return None, False
    finally:
        await context.close()


def _load_target_inns() -> list[str]:
    """Берём те компании, которые реально участвуют в ML candidate retrieval (FAISS index)."""
    if not INDEX_MAP.exists():
        _log(f"ГИСП fallback: не найден {INDEX_MAP}")
        return []
    inns: list[str] = []
    with INDEX_MAP.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            inn = re.sub(r"\D", "", str(row.get("supplier_inn") or ""))
            if len(inn) in (10, 12):
                inns.append(inn)
    return list(dict.fromkeys(inns))


def _load_cache() -> dict[str, dict]:
    if not MIRROR_CACHE.exists():
        return {}
    try:
        payload = json.loads(MIRROR_CACHE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_cache(cache: dict[str, dict]) -> None:
    MIRROR_CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = MIRROR_CACHE.with_suffix(".json.part")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, MIRROR_CACHE)


def _cache_fresh(entry: dict) -> bool:
    checked = entry.get("checked_at")
    if not checked:
        return False
    try:
        return datetime.fromisoformat(checked) >= datetime.now() - timedelta(days=CACHE_TTL_DAYS)
    except (TypeError, ValueError):
        return False


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


def _mirror_check_inn(inn: str) -> tuple[str, bool | None, str, str]:
    """manufacturer=None означает сетевую/HTTP ошибку, False — точного ИНН в active-реестре нет."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.6",
        "Cache-Control": "no-cache",
    }
    last_error = ""
    for attempt in range(2):
        try:
            r = requests.get(
                MIRROR_URL,
                params={"q": inn, "status": "active"},
                headers=headers,
                timeout=MIRROR_TIMEOUT,
                allow_redirects=True,
            )
            if r.status_code == 429:
                last_error = "HTTP 429"
                time.sleep(1.2 + attempt)
                continue
            if r.status_code >= 500:
                last_error = f"HTTP {r.status_code}"
                time.sleep(0.7 + attempt)
                continue
            if r.status_code != 200:
                return inn, None, "", f"HTTP {r.status_code}"

            text = _html_to_text(r.text)
            exact = bool(re.search(rf"\bИНН\s*:\s*{re.escape(inn)}\b", text, flags=re.I))
            if not exact:
                return inn, False, "", "ok"

            name = ""
            patterns = [
                rf"Производитель\s*:\s*(.+?)\s+Включ[её]н\s*:.*?\bИНН\s*:\s*{re.escape(inn)}\b",
                rf"Производитель\s*:\s*(.+?)\s+.*?\bИНН\s*:\s*{re.escape(inn)}\b",
            ]
            for pattern in patterns:
                m = re.search(pattern, text, flags=re.I | re.S)
                if m:
                    name = re.sub(r"\s+", " ", m.group(1)).strip(" -|;")[:500]
                    break
            return inn, True, name, "ok"
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt == 0:
                time.sleep(0.7)
    return inn, None, "", last_error or "request error"


def _make_partial_xlsx(rows: list[tuple[str, str]]) -> bytes:
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Производители")
    ws.append(["ИНН", "Наименование предприятия", "Источник", "Тип выгрузки"])
    for inn, name in rows:
        ws.append([inn, name, "tovarminpro.online (зеркало сведений ГИСП)", "partial-mirror"])
    meta = wb.create_sheet("META")
    meta.append(["Ключ", "Значение"])
    meta.append(["source", "tovarminpro.online"])
    meta.append(["coverage", "FAISS supplier_index_map"])
    meta.append(["generated_at", datetime.now().isoformat(timespec="seconds")])
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def _download_from_mirror() -> bytes | None:
    targets = _load_target_inns()
    if not targets:
        return None

    cache = _load_cache()
    resolved: dict[str, dict] = {}
    to_check: list[str] = []
    for inn in targets:
        entry = cache.get(inn) or {}
        if _cache_fresh(entry) and isinstance(entry.get("manufacturer"), bool):
            resolved[inn] = entry
        else:
            to_check.append(inn)

    _log(
        f"ГИСП fallback: официальный сайт недоступен. Проверяем публичное зеркало {MIRROR_URL} "
        f"для {len(targets):,} компаний из FAISS-пула; кэшировано {len(resolved):,}, новых проверок {len(to_check):,}."
    )

    completed = 0
    errors = 0
    if to_check:
        with ThreadPoolExecutor(max_workers=MIRROR_WORKERS) as pool:
            futures = {pool.submit(_mirror_check_inn, inn): inn for inn in to_check}
            for future in as_completed(futures):
                inn = futures[future]
                try:
                    _, manufacturer, name, detail = future.result()
                except Exception as exc:  # pragma: no cover - защита фонового процесса
                    manufacturer, name, detail = None, "", str(exc)
                if manufacturer is None:
                    errors += 1
                else:
                    entry = {
                        "manufacturer": bool(manufacturer),
                        "name": name,
                        "checked_at": datetime.now().isoformat(timespec="seconds"),
                        "source": "tovarminpro.online",
                    }
                    cache[inn] = entry
                    resolved[inn] = entry
                completed += 1
                if completed % 100 == 0 or completed == len(to_check):
                    positives = sum(1 for x in resolved.values() if x.get("manufacturer"))
                    _log(
                        f"ГИСП fallback: {completed:,}/{len(to_check):,} новых проверок; "
                        f"успешно разрешено {len(resolved):,}/{len(targets):,}; производителей {positives:,}; ошибок {errors:,}."
                    )
                    _save_cache(cache)

    _save_cache(cache)
    if len(resolved) < max(20, int(len(targets) * 0.55)):
        _log(
            f"ГИСП fallback: зеркало ответило только для {len(resolved):,}/{len(targets):,} компаний — "
            "недостаточно для безопасного применения."
        )
        return None

    manufacturers = sorted(
        ((inn, str(entry.get("name") or "")) for inn, entry in resolved.items() if entry.get("manufacturer")),
        key=lambda x: x[0],
    )
    if not manufacturers:
        _log("ГИСП fallback: в ответах зеркала не найдено ни одного производителя; результат не применяем.")
        return None

    _log(
        f"ГИСП fallback: сформирована частичная выгрузка: {len(manufacturers):,} подтверждённых производителей "
        f"из {len(resolved):,} проверенных компаний."
    )
    return _make_partial_xlsx(manufacturers)


async def download_registry(output: Path) -> bool:
    _log("ГИСП: старт синхронизации")
    output.parent.mkdir(parents=True, exist_ok=True)
    part = output.with_suffix(output.suffix + ".part")
    if part.exists():
        try:
            part.unlink()
        except OSError:
            pass

    official_blocked = False
    if _official_block_active():
        official_blocked = True
        _log(
            f"ГИСП: официальный источник недавно отвечал 403; пропускаем повторный browser-check на {OFFICIAL_BLOCK_HOURS} ч. "
            "и сразу используем кэш/fallback. Это ускоряет повторные синхронизации."
        )
    else:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
                )
                try:
                    for host in HOSTS:
                        _log(f"ГИСП: официальный источник {host}")
                        body, blocked = await _try_official_host(browser, host)
                        official_blocked = official_blocked or blocked
                        if body and _commit_xlsx(body, output):
                            _clear_official_block()
                            _log("ГИСП: использована официальная полная XLSX-выгрузка.")
                            return True
                        if blocked:
                            _remember_official_block()
                            # Домены находятся за одним защитным контуром; после явного 403
                            # не тратим время на повторную browser-навигацию.
                            break
                finally:
                    await browser.close()
        except Exception as exc:
            _log(f"ГИСП: Playwright/официальный источник недоступен: {exc}")

    if official_blocked:
        _log("ГИСП: автоматическая выгрузка официального сайта заблокирована HTTP 403. Запускаем безопасный fallback по публичному зеркалу.")
    else:
        _log("ГИСП: официальную XLSX получить не удалось. Запускаем fallback по публичному зеркалу.")

    mirror_body = await asyncio.to_thread(_download_from_mirror)
    if mirror_body and _commit_xlsx(mirror_body, output):
        _log("ГИСП: fallback-выгрузка подготовлена и будет применена как частичная (без сброса прежних подтверждений).")
        return True

    _log("ГИСП: не удалось получить данные ни из официальной XLSX, ни из fallback-зеркала. Старый registry.xlsx оставлен без изменений.")
    return False


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=Path("data/registry.xlsx"))
    ap.add_argument("--daemon", action="store_true")
    args = ap.parse_args()
    while True:
        ok = await download_registry(args.output)
        if not args.daemon:
            return 0 if ok else 1
        await asyncio.sleep(86_400)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
