import asyncio, os
import json
import re
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from tenacity import retry, stop_after_attempt, wait_fixed

load_dotenv()
TV_STORAGE = os.getenv("TV_STORAGE", "automation/storage_state.json")

# セレクタを直接定義
CHART_URL = "https://www.tradingview.com/chart/"
SEARCH_INPUT = "input[data-name='symbol-search-input'], input[aria-label='Symbol Search'], input[placeholder*='Symbol']"

# セレクタファイルをインポート
import sys

sys.path.append(os.path.dirname(__file__))

# Fibツールセレクタを直接定義
FIB_TOOL_BUTTONS = [
    # 描画ツールバーの具体的なセレクタ
    "button[data-name='linetool-fib-retracement']",
    "button[aria-label='Fib Retracement']",
    "button[aria-label*='Fibonacci Retracement']",
    "button[title*='Fib']",
    "button[title*='Fibonacci']",
    # ツールバーグループ内
    "[data-name*='linetool-group'] button[aria-label*='Fib']",
    "[data-name*='drawing-toolbar'] button[aria-label*='Fib']",
    # より広範囲なセレクタ
    "button[aria-label*='Fib']",
    "button:has-text('Fib')",
    "button[aria-label*='Retracement']",
    "button:has-text('リトレースメント')",
    # data-name属性ベース
    "[data-name*='fib']",
    "[data-name*='fibonacci']",
]


def TIMEFRAME_BUTTON(tf: str):
    return f"button[aria-label='{tf}'], button[aria-label*='{tf.upper()}'], button:has-text('{tf}')"


INDICATOR_BUTTONS = [
    "button[aria-label*='Indicators']",
    "button[aria-label*='Indicators & Strategies']",
    "button:has-text('Indicators')",
    "button:has-text('Indicators & Metrics')",
    "button:has-text('インジケーター')",
    "[data-name='open-indicators-dialog'] button",
]

INDICATOR_SEARCH = (
    "div[role='dialog'] input[placeholder*='Search'], "
    "div[role='dialog'] input[data-role='search'], "
    "div[role='dialog'] input[type='search']"
)

# 追加: ダイアログ内「Indicators on chart」一覧の×削除（できる範囲で）
INDICATORS_ON_CHART_TAB = (
    "div[role='dialog'] button:has-text('Indicators on chart'), "
    "div[role='dialog'] button:has-text('インジケーター（チャート）')"
)
REMOVE_ICON = "div[role='dialog'] [data-name='remove'] svg, div[role='dialog'] button[aria-label*='Remove']"

# ----- Indicator settings open (Legend path) -----
LEGEND_ITEM_BY_TEXT = (
    lambda text: f"div[data-name='legend-source-item']:has-text('{text}')"
)
LEGEND_SETTINGS_BTN = (
    "button[aria-label*='Settings'], [data-name='legend-settings-action']"
)

# ----- Indicator settings open (Dialog fallback) -----
INDICATORS_DIALOG = "div[role='dialog']"
INDICATORS_LIST_ROW = lambda text: f"{INDICATORS_DIALOG} :is(div,li):has-text('{text}')"
ROW_SETTINGS_BTN = "button[aria-label*='Settings'], [data-name='settings']"

# ----- Generic settings form controls -----
PARAM_LABEL = lambda label: f"{INDICATORS_DIALOG} label:has-text('{label}')"
PARAM_NUM_INPUT = (
    f"{INDICATORS_DIALOG} input[type='number'], "
    f"{INDICATORS_DIALOG} [role='spinbutton'], "
    f"{INDICATORS_DIALOG} input[inputmode='numeric']"
)
PARAM_TEXT_INPUT = f"{INDICATORS_DIALOG} input[type='text'], {INDICATORS_DIALOG} [contenteditable='true']"
PARAM_COMBO = (
    lambda label: f"{PARAM_LABEL(label)} ~ * [role='combobox'], {PARAM_LABEL(label)} ~ select"
)
COMBO_OPTION = (
    lambda text: f"[role='listbox'] div:has-text('{text}'), option:has-text('{text}')"
)

# ラベル別名（英/日 UI 両対応、必要に応じて追加）
LABEL_ALIASES = {
    "Length": ["Length", "期間"],
    "Source": ["Source", "ソース", "ソース/値", "ソース/価格"],
    "Fast Length": ["Fast Length", "短期"],
    "Slow Length": ["Slow Length", "長期"],
    "Signal Smoothing": ["Signal Smoothing", "シグナル平滑"],
}

# 設定OK/適用ボタン (英/日)
SETTINGS_OK = (
    f"{INDICATORS_DIALOG} button:has-text('OK'), "
    f"{INDICATORS_DIALOG} button:has-text('Apply'), "
    f"{INDICATORS_DIALOG} button:has-text('適用'), "
    f"{INDICATORS_DIALOG} button:has-text('OKを押す')"
)


@retry(stop=stop_after_attempt(2), wait=wait_fixed(2))
async def ensure_chart_ready(page):
    # 1) DOM, 2) main canvas visible, 3) 軽い遅延
    await page.wait_for_load_state("domcontentloaded")
    await page.locator("canvas").first.wait_for(state="visible", timeout=20000)
    await page.wait_for_timeout(600)


async def _safe_click_any(page, selectors: list[str], timeout=5000):
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            await loc.wait_for(state="visible", timeout=timeout)
            await loc.click()
            return True
        except Exception:
            continue
    return False


async def open_chart(context, symbol: str):
    page = await context.new_page()

    # 1) 課金/プラン遷移を通信レベルで遮断（最強の保険）
    await context.route(
        "**/*",
        lambda route: (
            route.abort()
            if any(
                x in route.request.url.lower()
                for x in [
                    "/checkout",
                    "/pricing",
                    "/upgrade",
                    "/plus",
                    "#order",
                    "/subscription",
                    "/plans",
                ]
            )
            else route.continue_()
        ),
    )

    await page.goto(CHART_URL)
    await ensure_chart_ready(page)
    # キャンバスにフォーカス
    await page.click("canvas", force=True)

    # シンボル検索（複数のアプローチを試行）
    symbol_search_success = False

    # 1) ホットキー "/" で検索
    try:
        await page.keyboard.press("/")
        await page.wait_for_selector(SEARCH_INPUT, timeout=3000)
        await page.fill(SEARCH_INPUT, symbol)
        await page.keyboard.press("Enter")
        symbol_search_success = True
    except PWTimeout:
        print("ホットキー検索失敗")

    # 2) 直接シンボル入力（ホットキーが効かない場合）
    if not symbol_search_success:
        try:
            await page.keyboard.press("/")
            await page.wait_for_timeout(1000)
            await page.keyboard.type(symbol)
            await page.keyboard.press("Enter")
            symbol_search_success = True
        except Exception:
            print("直接シンボル入力失敗")

    # 3) 検索ボタンを探してクリック
    if not symbol_search_success:
        try:
            symbol_button_selectors = [
                "button[aria-label*='Symbol']",
                "button[aria-label*='銘柄検索']",
                "button[data-tooltip*='Symbol']",
                "[data-name='symbol-search-button']",
            ]
            if await _safe_click_any(page, symbol_button_selectors, timeout=3000):
                await page.fill(SEARCH_INPUT, symbol)
                await page.keyboard.press("Enter")
                symbol_search_success = True
        except Exception:
            print("検索ボタンクリック失敗")

    if not symbol_search_success:
        print(f"警告: シンボル {symbol} の検索に失敗しました")

    await page.wait_for_timeout(1200)
    return page


async def set_timeframe(page, tf: str):
    try:
        await page.locator(TIMEFRAME_BUTTON(tf)).first.click(timeout=3000)
    except Exception:
        # ホットキーfallback（1,5,15,60,240, D）
        mapping = {"1m": "1", "5m": "5", "15m": "15", "1h": "60", "4h": "240", "D": "D"}
        key = mapping.get(tf, "60")
        await page.keyboard.type(str(key))
        await page.keyboard.press("Enter")
    await page.wait_for_timeout(400)


async def check_indicator_exists(page, indicator_name: str) -> bool:
    """インジケーターが既にチャートに存在するかチェック"""
    try:
        # インジケーターダイアログを開く
        opened = await open_indicators_dialog(page)
        if not opened:
            return False

        # "Indicators on chart"タブに切り替え
        try:
            await page.locator(INDICATORS_ON_CHART_TAB).first.click(timeout=1500)
            await page.wait_for_timeout(500)
        except Exception:
            pass

        # リスト内でインジケーター名を検索
        indicator_items = page.locator(
            "div[role='dialog'] div[role='listitem'], div[role='dialog'] div[class*='item']"
        )
        count = await indicator_items.count()

        for i in range(count):
            try:
                item = indicator_items.nth(i)
                text = await item.text_content()
                if indicator_name.lower() in text.lower():
                    return True
            except Exception:
                continue

        # ダイアログを閉じる
        await page.keyboard.press("Escape")
        return False
    except Exception:
        return False


async def open_settings_for_indicator(page, text_match: str) -> bool:
    # ① Legend 行 → 歯車（最優先）
    try:
        row = page.locator(LEGEND_ITEM_BY_TEXT(text_match)).first
        await row.wait_for(state="visible", timeout=2000)
        await row.hover()
        await row.locator(LEGEND_SETTINGS_BTN).first.click(timeout=1200)
        await page.wait_for_selector(INDICATORS_DIALOG, timeout=2500)
        return True
    except Exception:
        pass

    # ② Legend 行 → 右クリック → コンテキストメニュー「Settings」（UI差分用）
    try:
        row = page.locator(LEGEND_ITEM_BY_TEXT(text_match)).first
        await row.wait_for(state="visible", timeout=2000)
        await row.click(button="right")
        # メニューはロケール差分に備え英/日両方
        menu_sel = "div[role='menu'] div:has-text('Settings'), div[role='menu'] div:has-text('設定')"
        await page.locator(menu_sel).first.click(timeout=1200)
        await page.wait_for_selector(INDICATORS_DIALOG, timeout=2500)
        return True
    except Exception:
        pass

    # ③ ダイアログ → "Indicators on chart" → 行の歯車（フォールバック）
    try:
        # 既存の open_indicators_dialog があればそれを使ってOK
        opened = False
        for sel in INDICATOR_BUTTONS:
            try:
                await page.locator(sel).first.click(timeout=1500)
                opened = True
                break
            except Exception:
                continue
        if not opened:
            return False

        try:
            await page.locator(INDICATORS_ON_CHART_TAB).first.click(timeout=1500)
            await page.wait_for_timeout(300)
        except Exception:
            pass

        row = page.locator(INDICATORS_LIST_ROW(text_match)).first
        await row.wait_for(state="visible", timeout=2500)
        await row.locator(ROW_SETTINGS_BTN).first.click(timeout=1200)
        await page.wait_for_selector(INDICATORS_DIALOG, timeout=2500)
        return True
    except Exception:
        return False


def _label_candidates(label: str):
    # 指定ラベルに対する英/日候補列を返す
    return LABEL_ALIASES.get(label, [label])


async def _set_numeric(page, label: str, value):
    for lbl in _label_candidates(label):
        try:
            cand = page.locator(f"{PARAM_LABEL(lbl)} ~ {PARAM_NUM_INPUT}").first
            await cand.wait_for(state="visible", timeout=1000)
            await cand.fill(str(value))
            return True
        except Exception:
            # text/contenteditable fallback
            try:
                cand = page.locator(f"{PARAM_LABEL(lbl)} ~ {PARAM_TEXT_INPUT}").first
                await cand.wait_for(state="visible", timeout=800)
                await cand.click()
                await cand.fill(str(value))
                return True
            except Exception:
                continue
    return False


async def _set_select(page, label: str, option_text: str):
    for lbl in _label_candidates(label):
        try:
            combo = page.locator(PARAM_COMBO(lbl)).first
            await combo.wait_for(state="visible", timeout=1000)
            await combo.click()
            opt = page.locator(COMBO_OPTION(option_text)).first
            await opt.wait_for(state="visible", timeout=1000)
            await opt.click()
            return True
        except Exception:
            continue
    return False


async def _read_numeric(page, label: str):
    for lbl in _label_candidates(label):
        try:
            cand = page.locator(f"{PARAM_LABEL(lbl)} ~ {PARAM_NUM_INPUT}").first
            await cand.wait_for(state="visible", timeout=800)
            val = await cand.input_value()
            return val
        except Exception:
            try:
                cand = page.locator(f"{PARAM_LABEL(lbl)} ~ {PARAM_TEXT_INPUT}").first
                await cand.wait_for(state="visible", timeout=800)
                val = await cand.input_value()
                return val
            except Exception:
                continue
    return None


async def verify_indicator_params(page, expected: dict):
    """設定ダイアログが開いている前提。expected={'Length':200, 'Source':'close'}"""
    ok_map = {}
    for k, v in expected.items():
        val = await _read_numeric(page, k)
        if val is None:
            # select系の検証はTVの実装差で難しいので、ここは数値中心
            ok_map[k] = None
        else:
            ok_map[k] = str(v) == str(val)
    return ok_map


async def apply_indicator_params(page, indicator_match: str, params: dict):
    """設定ダイアログで params を適用。例: {'Length': 200, 'Source': 'close'}"""
    opened = await open_settings_for_indicator(page, indicator_match)
    if not opened:
        return {"ok": False, "reason": "settings_open_failed"}

    applied = {}
    for k, v in params.items():
        ok = False
        if isinstance(v, (int, float, str)) and (
            isinstance(v, (int, float)) or str(v).isdigit()
        ):
            ok = await _set_numeric(page, k, v)
            if not ok and isinstance(v, (str,)):
                # 数値に見える文字列はnumeric優先、だめならselectも試す
                ok = await _set_select(page, k, str(v))
        else:
            # 文字列は select を先に（Sourceなど）
            if isinstance(v, str):
                ok = await _set_select(page, k, v)
            if not ok:
                ok = await _set_numeric(page, k, v)

        applied[k] = bool(ok)

    # OK/Apply
    try:
        await page.locator(SETTINGS_OK).first.click(timeout=1200)
    except Exception:
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass

    # 再オープンして検証（簡易）
    verified = {}
    if await open_settings_for_indicator(page, indicator_match):
        verified = await verify_indicator_params(page, params)
        # 閉じる
        try:
            await page.locator(SETTINGS_OK).first.click(timeout=800)
        except Exception:
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass

    return {"ok": True, "applied": applied, "verified": verified}


async def add_indicator(page, name: str, params: dict = None):
    """インジケーターを追加（冪等化対応）"""
    # 既存チェック
    if await check_indicator_exists(page, name):
        print(f"インジケーター既に存在: {name}")
        return True

    # 1) ボタン複数候補から開く
    opened = await _safe_click_any(page, INDICATOR_BUTTONS, timeout=4000)
    if not opened:
        # 画面が狭いとメニュー化されることがある → コマンドパレット風メニュー経由 (Cmd/Ctrl + K) ※環境で効かない場合はスキップ
        try:
            await page.keyboard.press("Control+K")
        except Exception:
            pass

    # 2) 検索入力の出現を待つ
    try:
        await page.wait_for_selector(INDICATOR_SEARCH, timeout=5000)
        await page.fill(INDICATOR_SEARCH, name)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(500)
        # Escで閉じる
        await page.keyboard.press("Escape")

        # 3) パラメータ適用（指定がある場合）
        if params:
            await page.wait_for_timeout(1000)  # 描画待機
            await apply_indicator_params(page, name, params)

        return True
    except Exception:
        return False  # 呼び出し側でログる


async def open_indicators_dialog(page):
    # 開く
    for sel in INDICATOR_BUTTONS:
        try:
            await page.locator(sel).first.click(timeout=2000)
            break
        except Exception:
            continue
    # 検索欄 or ダイアログの出現を確認
    try:
        await page.wait_for_selector(INDICATOR_SEARCH, timeout=3000)
        return True
    except Exception:
        # 最低限、ダイアログ自体が出ていればOK
        try:
            await page.wait_for_selector("div[role='dialog']", timeout=2000)
            return True
        except Exception:
            return False


async def remove_all_indicators_on_chart(page):
    """ダイアログの 'Indicators on chart' タブからゴミ箱/×で既存インジを削除（最大10回）。"""
    opened = await open_indicators_dialog(page)
    if not opened:
        return False

    # タブ切り替え（ある場合のみ）
    try:
        await page.locator(INDICATORS_ON_CHART_TAB).first.click(timeout=1500)
        await page.wait_for_timeout(400)
    except Exception:
        pass  # タブが無いUIもある

    removed_any = False
    for _ in range(10):  # 無限ループ回避
        try:
            btn = page.locator(REMOVE_ICON).first
            await btn.wait_for(state="visible", timeout=1200)
            await btn.click()
            removed_any = True
            await page.wait_for_timeout(250)
        except Exception:
            break

    # ダイアログ閉じる
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass
    return removed_any


async def apply_preset(
    page,
    preset_name: str,
    clear_existing: bool = False,
    preset_path: str = "automation/indicators.json",
    skip_params: bool = False,
):
    """indicators.jsonからプリセットを読み、順次 add_indicator()（冪等化対応）。"""
    # 事前にキャンバスへフォーカス
    await page.click("canvas", force=True)

    # 既存インジ削除オプション
    if clear_existing:
        _ = await remove_all_indicators_on_chart(page)

    # プリセット読込
    path = Path(preset_path)
    if not path.exists():
        raise FileNotFoundError(f"preset file not found: {preset_path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    preset = data.get(preset_name)
    if not preset:
        raise ValueError(f"preset not found: {preset_name}")

    inds = preset.get("indicators", [])
    added = []
    for item in inds:
        # item は "Volume" のような str or {"name": "...", "params": {...}}
        if isinstance(item, str):
            ok = await add_indicator(page, item)
            if ok:
                added.append(item)
            else:
                print(f"[WARN] failed to add indicator: {item}")
        else:
            name = item.get("name")
            params = item.get("params", {})
            ok = await add_indicator(page, name)
            if ok:
                added.append(name)
                # skip_params が True の場合はパラメータ適用をスキップ（高速化）
                if params and not skip_params:
                    # ▼ ここで歯車→値適用
                    res = await apply_indicator_params(page, name, params)
                    if not res.get("ok"):
                        print(f"[WARN] failed to apply params for {name}: {res}")
                elif params and skip_params:
                    print(f"[SKIP] parameter tuning skipped for {name} (fast mode)")
            else:
                print(f"[WARN] failed to add indicator: {name}")

    # 重いレイアウトの場合は描画待機
    if len(added) > 2:
        await page.wait_for_timeout(1000)

    return {"preset": preset_name, "added": added, "requested": inds}


async def close_popups(page):
    """TradingViewのポップアップを自動で閉じる"""

    print("=== ポップアップ検出開始 ===")

    # 現在のURLをチェック
    current_url = page.url
    print(f"🌐 現在のURL: {current_url}")

    # プラン選択画面に遷移している場合は戻る
    if "plans" in current_url.lower() or "subscription" in current_url.lower():
        print("⚠️ プラン選択画面を検出。戻ります...")
        try:
            await page.go_back()
            await page.wait_for_timeout(2000)
            print("✅ 前のページに戻りました")
        except Exception as e:
            print(f"❌ ページ戻りでエラー: {e}")

    # ページの内容を確認
    try:
        page_title = await page.title()
        print(f"📄 ページタイトル: {page_title}")
    except Exception as e:
        print(f"❌ ページタイトル取得でエラー: {e}")

    # ポップアップ処理前のURLを記録
    original_url = page.url
    print(f"🔗 処理前URL: {original_url}")

    # まず、サブスクリプションポップアップの特定のテキストで検索
    subscription_texts = [
        "Take your subscription to the next level",
        "subscription",
        "upgrade",
        "premium",
    ]

    for text in subscription_texts:
        try:
            # テキストを含むダイアログ内のボタンを探す
            dialog = page.locator(f"div[role='dialog']:has-text('{text}')")
            if await dialog.count() > 0:
                print(f"✅ サブスクリプションポップアップを発見: {text}")

                # ダイアログ内のボタンを全て取得して内容を確認
                buttons = dialog.locator("button")
                count = await buttons.count()

                print(f"📊 ダイアログ内のボタン数: {count}")

                for i in range(count):
                    try:
                        button = buttons.nth(i)
                        button_text = await button.text_content()
                        print(f"🔘 ボタン {i+1}: '{button_text}'")

                        # 「Don't need」ボタンを優先的に探す
                        if (
                            "don't need" in button_text.lower()
                            or "don't" in button_text.lower()
                        ):
                            await button.click()
                            print(
                                f"✅ 「Don't need」ボタンをクリックしました: {button_text}"
                            )
                            await page.wait_for_timeout(500)

                            # URLの変化をチェック
                            new_url = page.url
                            if new_url != original_url:
                                print(
                                    f"⚠️ URLが変化しました: {original_url} → {new_url}"
                                )
                                print("🔄 前のURLに戻します...")
                                try:
                                    await page.go_back()
                                    await page.wait_for_timeout(2000)
                                    print("✅ 前のURLに戻りました")

                                    # 2) 戻った後のチャート健全性チェック
                                    await page.locator("canvas").first.wait_for(
                                        state="visible", timeout=5000
                                    )
                                    await page.locator(
                                        "div:has-text('Trading Panel')"
                                    ).first.wait_for(timeout=5000)
                                    print("✅ チャート健全性確認完了")
                                except Exception as e:
                                    print(f"❌ URL戻りでエラー: {e}")

                            return

                        # 「Show my options」ボタンは避ける
                        if (
                            "show my options" in button_text.lower()
                            or "show" in button_text.lower()
                        ):
                            print(
                                f"⚠️ 「Show my options」ボタンをスキップ: {button_text}"
                            )
                            continue

                        # その他の閉じる系ボタン
                        if any(
                            keyword in button_text.lower()
                            for keyword in [
                                "close",
                                "cancel",
                                "dismiss",
                                "skip",
                                "got",
                                "no thanks",
                            ]
                        ):
                            await button.click()
                            print(f"✅ 閉じるボタンをクリックしました: {button_text}")
                            await page.wait_for_timeout(500)

                            # URLの変化をチェック
                            new_url = page.url
                            if new_url != original_url:
                                print(
                                    f"⚠️ URLが変化しました: {original_url} → {new_url}"
                                )
                                print("🔄 前のURLに戻します...")
                                try:
                                    await page.go_back()
                                    await page.wait_for_timeout(2000)
                                    print("✅ 前のURLに戻りました")

                                    # 2) 戻った後のチャート健全性チェック
                                    await page.locator("canvas").first.wait_for(
                                        state="visible", timeout=5000
                                    )
                                    await page.locator(
                                        "div:has-text('Trading Panel')"
                                    ).first.wait_for(timeout=5000)
                                    print("✅ チャート健全性確認完了")
                                except Exception as e:
                                    print(f"❌ URL戻りでエラー: {e}")

                            return

                    except Exception as e:
                        print(f"❌ ボタン {i+1} の処理でエラー: {e}")
                        continue

                # 全てのボタンを確認した後、最後のボタン（通常「Don't need」）をクリック
                if count > 0:
                    try:
                        last_button = buttons.nth(count - 1)
                        last_button_text = await last_button.text_content()
                        print(f"🔄 最後のボタンをクリック: '{last_button_text}'")
                        await last_button.click()
                        print(f"✅ 最後のボタンをクリックしました: {last_button_text}")
                        await page.wait_for_timeout(500)

                        # URLの変化をチェック
                        new_url = page.url
                        if new_url != original_url:
                            print(f"⚠️ URLが変化しました: {original_url} → {new_url}")
                            print("🔄 前のURLに戻します...")
                            try:
                                await page.go_back()
                                await page.wait_for_timeout(2000)
                                print("✅ 前のURLに戻りました")

                                # 2) 戻った後のチャート健全性チェック
                                await page.locator("canvas").first.wait_for(
                                    state="visible", timeout=5000
                                )
                                await page.locator(
                                    "div:has-text('Trading Panel')"
                                ).first.wait_for(timeout=5000)
                                print("✅ チャート健全性確認完了")
                            except Exception as e:
                                print(f"❌ URL戻りでエラー: {e}")

                        return
                    except Exception as e:
                        print(f"❌ 最後のボタンクリックでエラー: {e}")

        except Exception as e:
            print(f"❌ テキスト '{text}' の検索でエラー: {e}")
            continue

    # より広範囲なポップアップ検索
    print("=== 広範囲ポップアップ検索開始 ===")

    # 全てのダイアログを検索
    try:
        all_dialogs = page.locator("div[role='dialog']")
        dialog_count = await all_dialogs.count()
        print(f"🔍 検出されたダイアログ数: {dialog_count}")

        for i in range(dialog_count):
            try:
                dialog = all_dialogs.nth(i)
                dialog_text = await dialog.text_content()
                print(f"📋 ダイアログ {i+1} の内容: {dialog_text[:200]}...")

                # ダイアログ内のボタンを確認
                buttons = dialog.locator("button")
                button_count = await buttons.count()
                print(f"🔘 ダイアログ {i+1} のボタン数: {button_count}")

                for j in range(button_count):
                    try:
                        button = buttons.nth(j)
                        button_text = await button.text_content()
                        print(f"  🔘 ボタン {j+1}: '{button_text}'")

                        # 「Don't need」ボタンを優先的に探す
                        if (
                            "don't need" in button_text.lower()
                            or "don't" in button_text.lower()
                        ):
                            await button.click()
                            print(
                                f"✅ 「Don't need」ボタンをクリックしました: {button_text}"
                            )
                            await page.wait_for_timeout(500)

                            # URLの変化をチェック
                            new_url = page.url
                            if new_url != original_url:
                                print(
                                    f"⚠️ URLが変化しました: {original_url} → {new_url}"
                                )
                                print("🔄 前のURLに戻します...")
                                try:
                                    await page.go_back()
                                    await page.wait_for_timeout(2000)
                                    print("✅ 前のURLに戻りました")

                                    # 2) 戻った後のチャート健全性チェック
                                    await page.locator("canvas").first.wait_for(
                                        state="visible", timeout=5000
                                    )
                                    await page.locator(
                                        "div:has-text('Trading Panel')"
                                    ).first.wait_for(timeout=5000)
                                    print("✅ チャート健全性確認完了")
                                except Exception as e:
                                    print(f"❌ URL戻りでエラー: {e}")

                            return

                        # 「Show my options」ボタンは避ける
                        if (
                            "show my options" in button_text.lower()
                            or "show" in button_text.lower()
                        ):
                            print(
                                f"⚠️ 「Show my options」ボタンをスキップ: {button_text}"
                            )
                            continue

                    except Exception as e:
                        print(f"❌ ボタン {j+1} の処理でエラー: {e}")
                        continue

            except Exception as e:
                print(f"❌ ダイアログ {i+1} の処理でエラー: {e}")
                continue

    except Exception as e:
        print(f"❌ 広範囲ポップアップ検索でエラー: {e}")

    print("=== 通常セレクタでの検索開始 ===")

    # 通常のセレクタで試行（フォールバック）
    popup_selectors = [
        # サブスクリプションポップアップ（エスケープ修正）
        "div[role='dialog'] button:has-text('Don\\'t need')",
        "div[role='dialog'] button:has-text('Don\\'t')",
        "div[role='dialog'] button:has-text('Close')",
        "div[role='dialog'] button:has-text('×')",
        "div[role='dialog'] button[aria-label='Close']",
        # より広範囲なセレクタ
        "div[role='dialog'] button",
        "div[class*='dialog'] button",
        "div[class*='modal'] button",
        # その他のポップアップ
        "div[role='dialog'] button:has-text('Got it')",
        "div[role='dialog'] button:has-text('Skip')",
        "div[role='dialog'] button:has-text('Not now')",
        "div[role='dialog'] button:has-text('Dismiss')",
        "div[role='dialog'] button:has-text('Cancel')",
        # 日本語UI対応
        "div[role='dialog'] button:has-text('閉じる')",
        "div[role='dialog'] button:has-text('キャンセル')",
        "div[role='dialog'] button:has-text('不要')",
        "div[role='dialog'] button:has-text('無視')",
    ]

    for selector in popup_selectors:
        try:
            # ポップアップが存在するかチェック
            popup = page.locator(selector).first
            if await popup.count() > 0:
                await popup.wait_for(state="visible", timeout=1000)
                await popup.click()
                print(f"✅ ポップアップを閉じました: {selector}")
                await page.wait_for_timeout(500)  # 閉じるアニメーション待機

                # URLの変化をチェック
                new_url = page.url
                if new_url != original_url:
                    print(f"⚠️ URLが変化しました: {original_url} → {new_url}")
                    print("🔄 前のURLに戻します...")
                    try:
                        await page.go_back()
                        await page.wait_for_timeout(2000)
                        print("✅ 前のURLに戻りました")

                        # 2) 戻った後のチャート健全性チェック
                        await page.locator("canvas").first.wait_for(
                            state="visible", timeout=5000
                        )
                        await page.locator(
                            "div:has-text('Trading Panel')"
                        ).first.wait_for(timeout=5000)
                        print("✅ チャート健全性確認完了")
                    except Exception as e:
                        print(f"❌ URL戻りでエラー: {e}")

                break
        except Exception as e:
            print(f"❌ セレクタ '{selector}' でエラー: {e}")
            continue

    print("=== Escapeキーでのフォールバック ===")

    # 追加: Escapeキーでポップアップを閉じる（フォールバック）
    try:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)
        print("✅ Escapeキーを押しました")
    except Exception as e:
        print(f"❌ Escapeキーでエラー: {e}")

    # さらに: 複数回Escapeを試行（ネストしたポップアップ対応）
    for i in range(3):
        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(200)
            print(f"✅ Escapeキー {i+1}回目")
        except Exception as e:
            print(f"❌ Escapeキー {i+1}回目でエラー: {e}")
            break

    print("=== ポップアップ検出完了 ===")


async def _get_plot_bbox(page):
    """プロット領域のバウンディングボックスを取得"""
    # いちばん上のパネルのcanvasを使う（必要なら nth(0) を変える）
    canvas = page.locator("canvas").first
    box = await canvas.bounding_box()
    if not box:
        raise RuntimeError("plot canvas not found")
    return box  # {x,y,width,height}


async def _price_to_y_converter(page):
    """
    価格軸のラベル（テキストとy座標）を複数取って、線形近似で price->y の変換関数を返す。
    """
    # 価格軸のラベルを探す（複数のセレクタを試行）
    price_selectors = [
        "div[data-name='price-axis'] span",
        "div[data-name='price-axis'] div",
        "div[class*='price'] span",
        "div[class*='price'] div",
        "div[class*='axis'] span",
        "div[class*='axis'] div",
    ]

    labs = None
    for selector in price_selectors:
        try:
            labs = page.locator(selector)
            count = await labs.count()
            if count > 0:
                break
        except Exception:
            continue

    if not labs:
        # フォールバック：簡易な価格→ピクセル変換
        def simple_price_to_y(price: float) -> float:
            # 画面の高さを基準に簡易変換
            viewport = page.viewport_size
            if not viewport:
                return 100.0
            # 価格範囲を仮定（USDJPYの場合）
            min_price = 140.0
            max_price = 160.0
            if price < min_price:
                price = min_price
            elif price > max_price:
                price = max_price
            # 線形変換
            ratio = (price - min_price) / (max_price - min_price)
            return viewport["height"] * (1 - ratio)  # 上から下へ

        return simple_price_to_y

    count = await labs.count()
    pts = []
    for i in range(min(count, 12)):
        el = labs.nth(i)
        txt = (await el.text_content() or "").strip()
        # 通貨記号など除去して float へ
        m = re.search(r"[-+]?\d+(\.\d+)?", txt.replace(",", ""))
        if not m:
            continue
        val = float(m.group(0))
        box = await el.bounding_box()
        if not box:
            continue
        y = box["y"]
        pts.append((val, y))

    if len(pts) < 2:
        # フォールバック：簡易な価格→ピクセル変換
        def simple_price_to_y(price: float) -> float:
            # 画面の高さを基準に簡易変換
            viewport = page.viewport_size
            if not viewport:
                return 100.0
            # 価格範囲を仮定（USDJPYの場合）
            min_price = 140.0
            max_price = 160.0
            if price < min_price:
                price = min_price
            elif price > max_price:
                price = max_price
            # 線形変換
            ratio = (price - min_price) / (max_price - min_price)
            return viewport["height"] * (1 - ratio)  # 上から下へ

        return simple_price_to_y

    # 近似：y = a*price + b（最小二乗）
    import numpy as np

    P = np.array([[p, 1.0] for p, _ in pts])
    Y = np.array([y for _, y in pts])
    a, b = np.linalg.lstsq(P, Y, rcond=None)[0]

    def price_to_y(price: float) -> float:
        return float(a * price + b)

    return price_to_y


async def _select_fib_tool(page, debug=False):
    """Fibツールを選択"""
    if debug:
        print("🔧 フィボナッチツール選択開始...")

    # 1) 描画ツールバーを表示させる（左側のツールバーアイコンをクリック）
    drawing_toolbar_selectors = [
        "button[aria-label*='Drawing']",
        "button[aria-label*='Tools']",
        "button[data-name*='drawing']",
        "button[data-name*='toolbar']",
        "[data-name='drawing-toolbar-button']",
        "[data-name='left-toolbar'] button",
    ]

    if debug:
        print("🎨 描画ツールバー表示を試行...")
    for sel in drawing_toolbar_selectors:
        try:
            await page.locator(sel).first.click(timeout=800, force=True)
            if debug:
                print(f"✅ 描画ツールバー表示成功: {sel}")
            break
        except Exception:
            continue

    # 少し待機してツールバーが表示されるのを待つ
    await page.wait_for_timeout(500)

    # 2) フィボナッチツールボタンを探してクリック
    for i, sel in enumerate(FIB_TOOL_BUTTONS):
        try:
            if debug:
                print(f"🔍 フィボツールボタン試行 {i+1}: {sel}")

            # 要素の存在を確認
            element = page.locator(sel).first
            await element.wait_for(state="visible", timeout=1000)
            await element.click(timeout=1200, force=True)

            if debug:
                print("✅ フィボツールボタンクリック成功")

            # ツール選択が成功したかを確認
            await page.wait_for_timeout(300)
            if debug:
                print("🔍 フィボツール選択状態を確認...")

            return True
        except Exception as e:
            if debug:
                print(f"❌ フィボツールボタン {i+1} 失敗: {e}")
            continue

    # 3) フォールバック：Alt+F
    if debug:
        print("🔄 Alt+Fホットキーを試行...")
    try:
        await page.keyboard.press("Alt+F")
        if debug:
            print("✅ Alt+F実行成功")
        return True
    except Exception as e:
        if debug:
            print(f"❌ Alt+F失敗: {e}")
        return False


async def draw_fibo_by_prices(
    page,
    high: float,
    low: float,
    x_ratio_start: float = 0.25,
    x_ratio_end: float = 0.75,
    direction: str = "high_to_low",
):
    """
    価格(高値/安値)を与えてフィボを描く。xはプロット幅の割合で置く。
    direction: 'high_to_low' | 'low_to_high'
    """
    box = await _get_plot_bbox(page)
    price_to_y = await _price_to_y_converter(page)

    # x座標：プロット領域の内側に割合で配置
    x1 = box["x"] + box["width"] * x_ratio_start
    x2 = box["x"] + box["width"] * x_ratio_end

    # y座標：価格を正確にピクセル化
    y_high = price_to_y(high)
    y_low = price_to_y(low)

    if direction == "high_to_low":
        start = (x1, y_high)
        end = (x2, y_low)
    else:
        start = (x1, y_low)
        end = (x2, y_high)

    # フィボツール選択前にページを安定させる
    await page.wait_for_timeout(500)

    ok = await _select_fib_tool(page, debug=True)
    if not ok:
        raise RuntimeError("Fib tool could not be selected")

    print(f"📍 フィボ描画座標: start={start}, end={end}")
    print(f"📊 価格範囲: high={high}, low={low}")

    # 描画（少しの待機を入れてからドラッグ）
    await page.wait_for_timeout(150)
    print("🖱️ マウス移動開始...")
    await page.mouse.move(*start)
    print(f"🖱️ マウスダウン: {start}")
    await page.mouse.down()
    print(f"🖱️ マウスドラッグ: {start} → {end}")
    await page.mouse.move(*end, steps=20)
    print("🖱️ マウスアップ")
    await page.mouse.up()

    # フィボナッチ描画の安定化待機（ESCキー無し）
    print("⏳ フィボナッチ描画の安定化を待機中...")
    await page.wait_for_timeout(2000)  # 2秒待機

    # ESCキーは使わない（フィボナッチが消去される可能性があるため）
    print("⚠️ フィボナッチ保持のためツール選択は維持...")

    print("✅ フィボナッチ描画完了（ツール選択維持）")
    return {"from": start, "to": end, "high": high, "low": low}


async def draw_fibo_quick(page, direction: str = "high_to_low"):
    """
    データ無しの簡易版：画面上部20%⇔下部80%を結んでフィボを引く。
    """
    box = await _get_plot_bbox(page)
    x1 = box["x"] + box["width"] * 0.25
    x2 = box["x"] + box["width"] * 0.75
    y_top = box["y"] + box["height"] * 0.18
    y_bot = box["y"] + box["height"] * 0.82
    start, end = (
        ((x1, y_top), (x2, y_bot))
        if direction == "high_to_low"
        else ((x1, y_bot), (x2, y_top))
    )
    ok = await _select_fib_tool(page, debug=True)
    if not ok:
        raise RuntimeError("Fib tool could not be selected")
    await page.mouse.move(*start)
    await page.mouse.down()
    await page.mouse.move(*end, steps=20)
    await page.mouse.up()

    # フィボナッチ描画の安定化待機（ESCキー無し）
    print("⏳ クイックフィボ描画の安定化を待機中...")
    await page.wait_for_timeout(2000)  # 2秒待機

    # ESCキーは使わない（フィボナッチが消去される可能性があるため）
    print("⚠️ フィボナッチ保持のためツール選択は維持...")

    return {"from": start, "to": end}


async def screenshot(page, outfile: str):
    """ポップアップを閉じてからスクショを撮る"""
    # 3) "見えてるけど押せない"系モーダルをCSSで無効化（最終フォールバック）
    await page.add_style_tag(
        content="""
      [class*='modal'], [class*='Dialog'], [role='dialog'] { display:none !important; }
    """
    )

    # ポップアップを閉じる
    await close_popups(page)

    # 少し待機してからスクショ
    await page.wait_for_timeout(1000)

    os.makedirs(os.path.dirname(outfile), exist_ok=True)
    await page.screenshot(path=outfile)
    return outfile


async def capture(
    symbol: str,
    tf: str = "1h",
    indicators=None,
    outfile="automation/screenshots/shot.png",
    headless=True,
    annotate: dict | None = None,
):
    indicators = indicators or []
    async with async_playwright() as p:
        # デバッグ快適化：ヘッドフル時はslow_mo追加
        browser_options = {"headless": headless}
        if not headless:
            browser_options["slow_mo"] = 150

        browser = await p.chromium.launch(**browser_options)
        context = await browser.new_context(
            storage_state=TV_STORAGE if os.path.exists(TV_STORAGE) else None,
            viewport={"width": 1600, "height": 900},
        )
        page = await open_chart(context, symbol)

        # 既定タイムアウトを引き上げ
        page.set_default_timeout(45000)

        await set_timeframe(page, tf)

        for ind in indicators:
            ok = await add_indicator(page, ind)
            if not ok:
                print(f"[WARN] インジ追加失敗: {ind}")

        path = await screenshot(page, outfile)

        # ▼ 注釈（QuietTrapなど）— 画像後処理
        if annotate and annotate.get("quiet_trap"):
            try:
                from annotate import annotate_quiet_trap
            except Exception:
                # 明示パスでimport（python実行ディレクトリ差分対策）
                import importlib.util, sys

                ap = Path(__file__).parent / "annotate.py"
                spec = importlib.util.spec_from_file_location("annotate", ap)
                mod = importlib.util.module_from_spec(spec)
                sys.modules["annotate"] = mod
                spec.loader.exec_module(mod)
                annotate_quiet_trap = getattr(mod, "annotate_quiet_trap")

            qt = annotate["quiet_trap"]
            side = qt.get("side", "sell")
            score = float(qt.get("score", 0.0))
            notes = qt.get("notes", [])
            footer = qt.get("footer")
            annotate_quiet_trap(outfile, side, score, notes, footer)

        await browser.close()
        return path


if __name__ == "__main__":
    # デバッグ時は headless=False 推奨
    out = asyncio.run(
        capture(
            "USDJPY",
            "1h",
            ["Relative Strength Index", "Volume"],
            "automation/screenshots/usdjpy_1h.png",
            headless=False,
        )
    )
    print("[OK] saved:", out)
