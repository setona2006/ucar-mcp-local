import asyncio
import os
from playwright.async_api import async_playwright
from tv_controller import apply_preset


async def test_preset_v2():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=False)
        ctx = await b.new_context(
            storage_state=os.getenv("TV_STORAGE", "automation/storage_state.json")
        )
        page = await ctx.new_page()
        await page.goto("https://www.tradingview.com/chart/")

        print("Preset v2 'rsi_vol_ma200' を適用中...")
        result = await apply_preset(page, "rsi_vol_ma200", clear_existing=True)
        print(f"結果: {result}")

        await page.screenshot(path="automation/screenshots/preset_v2_test.png")
        print("スクリーンショット保存: automation/screenshots/preset_v2_test.png")
        await b.close()


if __name__ == "__main__":
    asyncio.run(test_preset_v2())
