import asyncio, os
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

TV_EMAIL = os.getenv("TV_EMAIL")
TV_PASSWORD = os.getenv("TV_PASSWORD")
TV_STORAGE = os.getenv("TV_STORAGE", "automation/storage_state.json")
TV_URL = "https://www.tradingview.com/"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # 初回はFalse
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(TV_URL, wait_until="domcontentloaded")

        # 画面右上のログイン
        await page.get_by_role("button", name="Log in").click()
        # "Email"ログインを選ぶ（UI変更に合わせて調整）
        await page.get_by_role("button", name="Email").click()

        await page.get_by_placeholder("Email").fill(TV_EMAIL)
        await page.get_by_placeholder("Password").fill(TV_PASSWORD)
        await page.get_by_role("button", name="Sign in").click()

        # 2FAがある場合は待機/手動入力 or 別実装
        await page.wait_for_load_state("networkidle")
        await ctx.storage_state(path=TV_STORAGE)
        print(f"[OK] Saved storage to: {TV_STORAGE}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
