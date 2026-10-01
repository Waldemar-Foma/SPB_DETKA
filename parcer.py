import time
import asyncio
import pandas as pd
from playwright.async_api import async_playwright

async def download_registry_securely():
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Запуск скачивания реестра Минпромторга...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            # 1. Заходим на главную, чтобы Qrator проверил браузер и выдал токены
            print("Проходим проверку защиты Qrator...")
            await page.goto("https://gisp.gov.ru/pp719v2/pub/prod/", wait_until="domcontentloaded")
            await asyncio.sleep(3) # Даем JS-скриптам защиты пару секунд на отработку
            
            print("Токены получены. Запрашиваем файл реестра...")
            # 2. Ждем скачивания
            async with page.expect_download(timeout=120000) as download_info:
                try:
                    await page.goto("https://gisp.gov.ru/pp719v2/mptapp/view/dl/production_res_valid_only/")
                except Exception as goto_err:
                    # Игнорируем панику Playwright о том, что началась загрузка файла
                    if "Download is starting" not in str(goto_err):
                        raise goto_err
            
            download = await download_info.value
            await download.save_as("registry.xlsx")
            
            # Читаем скачанный файл
            df = pd.read_excel("registry.xlsx")
            print(f"Успех! База обновлена. Всего производителей: {len(df)}")
            
            await browser.close()
            
    except Exception as e:
        print(f"Сбой при скачивании реестра: {e}")

async def main():
    print("Старт фонового воркера...")
    while True:
        # 1. Запускаем скачивание
        await download_registry_securely()
        
        # 2. Уходим в спящий режим на 24 часа
        wait_time = 86400
        print("Переход в режим ожидания. Следующее обновление начнется через 24 часа.")
        await asyncio.sleep(wait_time)

if __name__ == "__main__":
    # Запускаем главный асинхронный цикл
    asyncio.run(main())
