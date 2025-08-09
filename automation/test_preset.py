import asyncio
import os
from playwright.async_api import async_playwright
from tv_controller import apply_preset


async def test_preset():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=False)
        ctx = await b.new_context(
            storage_state=os.getenv("TV_STORAGE", "automation/storage_state.json")
        )
        page = await ctx.new_page()
        await page.goto("https://www.tradingview.com/chart/")

        print("プリセット 'rsi_vol_ma' を適用中...")
        result = await apply_preset(page, "rsi_vol_ma", clear_existing=True)
        print(f"結果: {result}")

        await page.screenshot(path="automation/screenshots/preset_test.png")
        print("スクリーンショット保存: automation/screenshots/preset_test.png")
        await b.close()


if __name__ == "__main__":
    asyncio.run(test_preset())
