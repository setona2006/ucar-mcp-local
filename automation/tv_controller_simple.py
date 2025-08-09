TradingViewのチャートページは非常に重いため、networkidleの待機を省略して、より軽量なアプローチを試してみましょう：import asyncio, os, time
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

load_dotenv()
TV_STORAGE = os.getenv("TV_STORAGE", "automation/storage_state.json")

# セレクタを直接定義
CHART_URL = "https://www.tradingview.com/chart/"
SEARCH_INPUT = "input[data-name='symbol-search-input']"
INDICATOR_BUTTON = "button[aria-label='Indicators']"
INDICATOR_SEARCH = "input[data-role='search']"


async def open_chart(context, symbol: str):
    page = await context.new_page()
    print(f"チャートページにアクセス中: {CHART_URL}")

    # より軽量な待機設定
    await page.goto(CHART_URL, wait_until="domcontentloaded", timeout=60000)
    print("ページ読み込み完了")

    # チャートの読み込みを待つ
    await page.wait_for_timeout(5000)
    print("チャート読み込み待機完了")

    # シンボル入力
    try:
        print(f"シンボル検索中: {symbol}")
        await page.keyboard.press("/")
        await page.wait_for_selector(SEARCH_INPUT, timeout=5000)
        await page.fill(SEARCH_INPUT, symbol)
        await page.keyboard.press("Enter")
        print("シンボル検索完了")
    except PWTimeout:
        print("ホットキー検索失敗、直接検索を試行")
        try:
            await page.click("button[aria-label='Symbol Search']")
            await page.fill(SEARCH_INPUT, symbol)
            await page.keyboard.press("Enter")
        except:
            print("直接検索も失敗、手動入力で対応")
            # 最後の手段：手動でシンボルを入力
            await page.keyboard.press("/")
            await page.wait_for_timeout(1000)
            await page.keyboard.type(symbol)
            await page.keyboard.press("Enter")

    await page.wait_for_timeout(3000)  # チャート読み込み待機
    print("チャート読み込み完了")
    return page


async def set_timeframe(page, tf: str):
    print(f"時間足設定中: {tf}")
    # ホットキーを使用（より安定）
    mapping = {"1m": "1", "5m": "5", "15m": "15", "1h": "60", "4h": "240", "D": "D"}
    key = mapping.get(tf, "60")
    await page.keyboard.type(key)
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(1000)
    print("時間足設定完了")


async def add_indicator(page, name: str):
    print(f"インジケーター追加中: {name}")
    try:
        await page.click(INDICATOR_BUTTON)
        await page.wait_for_selector(INDICATOR_SEARCH, timeout=5000)
        await page.fill(INDICATOR_SEARCH, name)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(1000)
        # 閉じる（Esc）
        await page.keyboard.press("Escape")
        print(f"インジケーター追加完了: {name}")
    except Exception as e:
        print(f"インジケーター追加失敗: {name} - {e}")


async def screenshot(page, outfile: str):
    print(f"スクリーンショット保存中: {outfile}")
    os.makedirs(os.path.dirname(outfile), exist_ok=True)
    await page.screenshot(path=outfile, full_page=False)
    return outfile


async def capture(
    symbol: str,
    tf: str = "1h",
    indicators: list[str] | None = None,
    outfile: str = "automation/screenshots/shot.png",
):
    print(f"=== TradingView チャートキャプチャ開始 ===")
    print(f"シンボル: {symbol}")
    print(f"時間足: {tf}")
    print(f"インジケーター: {indicators or []}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=TV_STORAGE if os.path.exists(TV_STORAGE) else None
        )

        try:
            page = await open_chart(context, symbol)
            await set_timeframe(page, tf)
            if indicators:
                for ind in indicators:
                    await add_indicator(page, ind)
            path = await screenshot(page, outfile)
            print(f"=== キャプチャ完了: {path} ===")
            return path
        except Exception as e:
            print(f"エラーが発生しました: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    # 単体テスト：USDJPY 1h + RSI/Volume
    out = asyncio.run(
        capture(
            "USDJPY",
            "1h",
            ["Relative Strength Index", "Volume"],
            "automation/screenshots/usdjpy_1h.png",
        )
    )
    print("[OK] saved:", out)
