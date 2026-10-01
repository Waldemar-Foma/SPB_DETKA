"""Скачивание реестра ГИСП/Минпромторга через Playwright.

Скрипт возвращает ненулевой exit-code при ошибке: это важно, чтобы сайт и
SYNC_GISP.bat не считали старый файл успешной новой синхронизацией.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import time
from pathlib import Path

from playwright.async_api import async_playwright

CATALOG_URL = "https://gisp.gov.ru/pp719v2/pub/prod/"
DOWNLOAD_URL = "https://gisp.gov.ru/pp719v2/mptapp/view/dl/production_res_valid_only/"


def _looks_like_xlsx(data: bytes) -> bool:
    # XLSX — ZIP-контейнер и обычно существенно больше пары килобайт.
    return len(data) > 10_000 and data[:2] == b"PK"


async def download_registry(output: Path) -> bool:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ГИСП: старт", flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".part")
    try:
        if tmp.exists():
            tmp.unlink()
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
                ),
                locale="ru-RU",
            )
            page = await context.new_page()
            await page.goto(CATALOG_URL, wait_until="domcontentloaded", timeout=120_000)
            await page.wait_for_timeout(1800)

            # Сначала пробуем получить файл через request-context браузера —
            # так сохраняются cookies/session, но нет зависимости от UI кнопки.
            try:
                response = await context.request.get(DOWNLOAD_URL, timeout=120_000)
                body = await response.body() if response.ok else b""
                if _looks_like_xlsx(body):
                    tmp.write_bytes(body)
                    os.replace(tmp, output)
                    print(f"ГИСП сохранён: {output} ({len(body) / 1024 / 1024:.1f} МБ)", flush=True)
                    return True
                print(f"ГИСП: прямой ответ не похож на XLSX (HTTP {response.status}, {len(body)} байт), пробуем browser download", flush=True)
            except Exception as exc:
                print(f"ГИСП: request-context не сработал: {exc}", flush=True)

            # Fallback: браузерная загрузка.
            try:
                async with page.expect_download(timeout=120_000) as info:
                    try:
                        await page.goto(DOWNLOAD_URL, wait_until="commit", timeout=120_000)
                    except Exception as exc:
                        # Chromium нередко выбрасывает ERR_ABORTED, когда navigation
                        # превращается в download — в этом случае expect_download всё равно срабатывает.
                        if "Download is starting" not in str(exc) and "ERR_ABORTED" not in str(exc):
                            raise
                download = await info.value
                await download.save_as(str(tmp))
                data = tmp.read_bytes()
                if not _looks_like_xlsx(data):
                    raise RuntimeError(f"Скачанный файл не похож на XLSX: {len(data)} байт")
                os.replace(tmp, output)
                print(f"ГИСП сохранён: {output} ({len(data) / 1024 / 1024:.1f} МБ)", flush=True)
                return True
            finally:
                await browser.close()
    except Exception as exc:
        print(f"ГИСП: ошибка: {exc}", flush=True)
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
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
