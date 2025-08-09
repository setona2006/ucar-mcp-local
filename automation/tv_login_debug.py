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
        browser = await p.chromium.launch(headless=False)  # 必ずヘッドフルで確認
        ctx = await browser.new_context()
        page = await ctx.new_page()

        print("TradingViewにアクセス中...")
        await page.goto(TV_URL, wait_until="domcontentloaded")
        print("ページ読み込み完了")

        # ページの構造を確認
        print("\n=== ページ構造の確認 ===")

        # ログインボタンの候補を探す
        login_selectors = [
            'button[data-name="header-sign-in-button"]',
            'button[aria-label="Sign in"]',
            'button:has-text("Log in")',
            'button:has-text("Sign in")',
            'a[href*="sign-in"]',
            '[data-name="header-sign-in-button"]',
        ]

        for selector in login_selectors:
            try:
                element = await page.wait_for_selector(selector, timeout=2000)
                if element:
                    print(f"✅ 見つかった: {selector}")
                    text = await element.text_content()
                    print(f"   テキスト: {text}")
                else:
                    print(f"❌ 見つからない: {selector}")
            except:
                print(f"❌ 見つからない: {selector}")

        # ページのHTMLを少し確認
        print("\n=== ページタイトル ===")
        title = await page.title()
        print(f"タイトル: {title}")

        print("\n=== 手動操作の準備完了 ===")
        print("ブラウザが開きました。手動でログインしてください。")
        print("ログイン後、Enterキーを押してください...")

        # 手動操作を待つ
        input()

        # ログイン後の状態を保存
        await ctx.storage_state(path=TV_STORAGE)
        print(f"[OK] Saved storage to: {TV_STORAGE}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
