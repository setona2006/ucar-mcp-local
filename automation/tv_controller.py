import asyncio, os
import json
import re
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from tenacity import retry, stop_after_attempt, wait_fixed
import contextlib

load_dotenv()
TV_STORAGE = os.getenv("TV_STORAGE", "automation/storage_state.json")

# セレクタを直接定義
CHART_URL = "https://www.tradingview.com/chart/"
SEARCH_INPUT = "input[data-name='symbol-search-input'], input[aria-label='Symbol Search'], input[placeholder*='Symbol']"

# セレクタファイルをインポート
import sys

sys.path.append(os.path.dirname(__file__))

# Fibツールセレクタは selectors.py を優先利用（失敗時はローカル定義をフォールバック）
try:
    from selectors import FIB_TOOL_BUTTONS as FIB_TOOL_BUTTONS  # type: ignore
except Exception:
    FIB_TOOL_BUTTONS = [
        # 具体的なデータ名/ラベル
        "button[data-name='linetool-fib-retracement']",
        "button[aria-label='Fib Retracement']",
        "button[aria-label*='Fibonacci Retracement']",
        "[data-name='linetool-fib-retracement']",
        "[data-name*='fib-retracement']",
        # タイトル属性
        "button[title*='Fib']",
        "button[title*='Fibonacci']",
        # 一般的なaria-label/テキスト
        "button[aria-label*='Fib']",
        "button[aria-label*='Retracement']",
        "button:has-text('Fib')",
        "button:has-text('リトレースメント')",
        "[role='button'][aria-label*='Fib']",
        "div[role='toolbar'] [aria-label*='Fib']",
        "[class*='button']:has-text('Fib')",
        # ツールバーグループ内の候補
        "[data-name*='linetool-group'] button[aria-label*='Fib']",
        "[data-name*='drawing-toolbar'] button[aria-label*='Fib']",
        # data-name属性ベース（広め）
        "[data-name*='linetool-fib']",
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


# ======= Anti popup (preempt + fast) =======
# CSS/JS を初期ロードで注入して、出現を抑制＆即時クリック
ANTI_POPUP_CSS = """
[role="dialog"], [class*="modal"], [data-name*="popup"], [data-dialog-name*="subscription"] {
  display: none !important;
  visibility: hidden !important;
  pointer-events: none !important;
}
"""

ANTI_POPUP_JS = r"""
(() => {
  const prefer = [
    /don't need/i, /no thanks/i, /not now/i, /skip/i, /close/i, /dismiss/i,
    /閉じる/, /不要/, /キャンセル/
  ];
  const clickCandidates = () => {
    const btns = Array.from(document.querySelectorAll('div[role="dialog"] button, [class*="modal"] button'));
    for (const b of btns) {
      const t = (b.innerText || b.textContent || '').trim();
      if (prefer.some(r => r.test(t))) {
        try { b.click(); } catch {}
      }
    }
  };
  // 初回 & 監視
  clickCandidates();
  const mo = new MutationObserver(() => clickCandidates());
  mo.observe(document.documentElement, { childList: true, subtree: true });
})();
"""


async def install_anti_popup(context):
    """Network abort + init CSS/JS to prevent and auto-dismiss popups."""
    # 1) 通信層で危険URLを遮断
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
                    "/subscription",
                    "/plans",
                    "#order",
                ]
            )
            else route.continue_()
        ),
    )
    # 2) 読込前スクリプト（JSとCSS）を注入
    await context.add_init_script(ANTI_POPUP_JS)
    await context.add_init_script(
        f"""
        (() => {{
          const s = document.createElement('style');
          s.textContent = `{ANTI_POPUP_CSS}`;
          document.documentElement.appendChild(s);
        }})();
        """
    )


async def _set_overlap_pointer_events(page, enable: bool):
    """Temporarily disable pointer events on overlap-manager to avoid intercepts."""
    css_id = "ucar-kill-overlap"
    if enable:
        css = """
        #overlap-manager-root, #overlap-manager-root-1,
        #overlap-manager-root *, #overlap-manager-root-1 * {
          pointer-events: none !important;
        }
        """
        await page.add_style_tag(content=css, id=css_id)
    else:
        # Remove previously injected style
        await page.evaluate(
            """
            (id) => {
              const el = document.getElementById(id);
              if (el && el.parentElement) el.parentElement.removeChild(el);
            }
            """,
            css_id,
        )


async def clear_overlays_aggressively(page):
    """Remove common dialogs/backdrops/overlays that may intercept pointer."""
    js = r"""
    (() => {
      const kill = (el) => { if (!el) return; el.style.display='none'; el.style.visibility='hidden'; el.style.pointerEvents='none'; el.setAttribute('data-killed','1'); };
      const sels = [
        'div[role="dialog"]', '[class*="modal"]', '[class*="overlay"]', '[class*="backdrop"]',
        '[data-name*="popup"]', '[data-dialog-name]', '[data-name*="dialog"]',
        '#overlap-manager-root > *', '#overlap-manager-root-1 > *'
      ];
      for (const sel of sels) document.querySelectorAll(sel).forEach(kill);
    })();
    """
    try:
        await page.evaluate(js)
    except Exception:
        pass


async def _toggle_overlap_hidden(page, enable: bool):
    """Hide/show overlap-manager roots entirely to avoid any intercepts."""
    css_id = "ucar-hide-overlap"
    if enable:
        css = """
        #overlap-manager-root, #overlap-manager-root-1 {
          display: none !important;
        }
        """
        await page.evaluate(
            """
            (id, css) => {
              let s = document.getElementById(id);
              if (!s) {
                s = document.createElement('style');
                s.id = id;
                document.documentElement.appendChild(s);
              }
              s.textContent = css;
            }
            """,
            css_id,
            css,
        )
    else:
        await page.evaluate(
            """
            (id) => {
              const s = document.getElementById(id);
              if (s && s.parentElement) s.parentElement.removeChild(s);
            }
            """,
            css_id,
        )


async def _lock_last_drawing(page):
    """選択中の描画オブジェクトをロック（浮遊ツールバーの鍵アイコンをクリック）。"""
    candidates = [
        "[data-name='floating-toolbar'] [data-name*='lock']",
        "[data-name='floating-toolbar'] button[aria-label*='Lock']",
        "[data-name='floating-toolbar'] [class*='lock']",
    ]
    for sel in candidates:
        try:
            await page.locator(sel).first.click(timeout=600, force=True)
            await page.wait_for_timeout(120)
            return True
        except Exception:
            continue
    return False


async def _wait_floating_toolbar(page, timeout=1500) -> bool:
    try:
        await page.locator("[data-name='floating-toolbar']").first.wait_for(
            state="visible", timeout=timeout
        )
        return True
    except Exception:
        return False


async def _lock_by_context_menu(page, at_x: float, at_y: float) -> bool:
    try:
        await page.mouse.move(at_x, at_y)
        await page.mouse.click(at_x, at_y, button="right")
        menu_sel = "div[role='menu'] div:has-text('Lock'), div[role='menu'] div:has-text('ロック')"
        await page.locator(menu_sel).first.click(timeout=1000)
        await page.wait_for_timeout(150)
        return True
    except Exception:
        return False


async def _lock_all_drawings_toggle(page, enable: bool) -> bool:
    """左ツールバーの全描画ロック切り替え（UI差分に対し複数候補）。"""
    selectors = [
        "[aria-label*='Lock all drawings']",
        "[aria-label*='Lock All']",
        "[data-name*='lock-all']",
        "button:has-text('Lock all')",
        "button:has-text('すべてロック')",
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            await btn.wait_for(state="visible", timeout=800)
            # 状態判定は難しいため2回押して戻す方法は避け、enable=Trueなら一度押す前に右クリックメニューでLock AllがONか確認…は重いので簡易化
            await btn.click(timeout=800, force=True)
            await page.wait_for_timeout(120)
            return True
        except Exception:
            continue
    return False


async def _js_force_click(page, selector: str, timeout_ms: int = 1500) -> bool:
    """Click by executing element.click() in page context to bypass pointer intercepts."""
    try:
        el = page.locator(selector).first
        await el.wait_for(state="attached", timeout=timeout_ms)
        # Ensure in DOM then click via JS
        await page.evaluate(
            "el => { try { el.click(); } catch(e) {} }",
            await el.element_handle(),
        )
        return True
    except Exception:
        return False


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

    # Anti-popup を必ず最初に仕込む（表示前に効かせる）
    try:
        await install_anti_popup(context)
    except Exception:
        pass

    await page.goto(CHART_URL)
    await ensure_chart_ready(page)
    # キャンバスにフォーカス & オーバーレイ強制排除
    await page.click("canvas", force=True)
    await page.add_style_tag(content=ANTI_POPUP_CSS)
    try:
        await close_popups_fast(page)
    except Exception:
        pass

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


async def verify_indicator_params(page, expected: dict) -> dict[str, bool | None]:
    """設定ダイアログが開いている前提。expected={'Length':200, 'Source':'close'}"""
    ok_map: dict[str, bool | None] = {}
    for k, v in expected.items():
        val = await _read_numeric(page, k)
        if val is None:
            # select系の検証はTVの実装差で難しいので、ここは数値中心
            ok_map[k] = None
        else:
            ok_map[k] = str(v) == str(val)
    return ok_map


async def apply_indicator_params(page, indicator_match: str, params: dict) -> dict:
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


async def add_indicator(page, name: str, params: dict | None = None):
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
    """Back-compat slow closer (kept for reference). Prefer close_popups_fast."""
    # 互換維持のため簡略化して即座にエスケープだけ打つ
    try:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(50)
    except Exception:
        pass
    return


import time
from contextlib import suppress


async def close_popups_fast(page, budget_ms: int | None = None):
    """並列・時間上限つきの高速ポップアップ排除。
    budget_ms: 上限ミリ秒（環境変数 POPUP_BUDGET_MS が優先）
    """
    if budget_ms is None:
        try:
            budget_ms = int(os.getenv("POPUP_BUDGET_MS", "800"))
        except Exception:
            budget_ms = 800

    start = time.perf_counter()

    async def _click_prefer_buttons():
        labels = [
            "Don't need",
            "No thanks",
            "Not now",
            "Skip",
            "Close",
            "Dismiss",
            "閉じる",
            "不要",
            "キャンセル",
        ]
        for text in labels:
            with suppress(Exception):
                await page.get_by_role("button", name=text, exact=False).first.click(
                    timeout=150
                )
                return True
        # 汎用dialog内ボタン
        with suppress(Exception):
            await page.locator("div[role='dialog'] button").first.click(timeout=150)
            return True
        return False

    async def _click_close_icon():
        sels = [
            "button[aria-label*='close']",
            "button[title*='close']",
            "button:has-text('×')",
        ]
        for s in sels:
            with suppress(Exception):
                await page.locator(s).first.click(timeout=120)
                return True
        return False

    async def _spam_escape():
        with suppress(Exception):
            for _ in range(3):
                await page.keyboard.press("Escape")
            await page.wait_for_timeout(50)
            return True
        return False

    async def _healthy():
        try:
            await page.locator("div[data-name='pane'] canvas").first.wait_for(
                state="visible", timeout=200
            )
            return True
        except Exception:
            return False

    tasks = [
        asyncio.create_task(_click_prefer_buttons()),
        asyncio.create_task(_click_close_icon()),
        asyncio.create_task(_spam_escape()),
    ]

    try:
        done, pending = await asyncio.wait(
            tasks, timeout=budget_ms / 1000, return_when=asyncio.FIRST_COMPLETED
        )
        for p in pending:
            p.cancel()
    finally:
        pass

    ok = await _healthy()
    elapsed = int((time.perf_counter() - start) * 1000)
    print(f"[close_popups_fast] {elapsed}ms, healthy={ok}")
    return ok


async def go_back_if_navigated(page, original_url: str):
    """URLが変化してしまった場合に素早く戻る（軽量待機）。"""
    if page.url != original_url:
        try:
            await page.go_back()
            await page.wait_for_load_state("domcontentloaded", timeout=800)
        except Exception:
            pass


async def _get_plot_bbox(page):
    """プロット領域のバウンディングボックスを取得"""
    # 可能ならメインチャート（最後のpaneのcanvas）を使う
    panes = page.locator("div[data-name='pane'] canvas")
    try:
        count = await panes.count()
    except Exception:
        count = 0

    target = (
        panes.nth(count - 1) if count and count > 0 else page.locator("canvas").first
    )
    box = await target.bounding_box()
    if not box or box.get("height", 0) < 80:
        # フォールバック: 先頭canvas
        target = page.locator("canvas").first
        box = await target.bounding_box()
    if not box:
        raise RuntimeError("plot canvas not found")
    return box  # {x,y,width,height}


async def _focus_plot_canvas(page):
    """ターゲットのプロットcanvasに確実にフォーカスを当てる"""
    panes = page.locator("div[data-name='pane'] canvas")
    try:
        count = await panes.count()
    except Exception:
        count = 0
    target = (
        panes.nth(count - 1) if count and count > 0 else page.locator("canvas").first
    )
    box = await target.bounding_box()
    if box:
        cx = box["x"] + box["width"] * 0.5
        cy = box["y"] + box["height"] * 0.5
        try:
            await page.mouse.move(cx, cy)
            await page.mouse.click(cx, cy, delay=40)
        except Exception:
            # フォールバック: 単純クリック
            await target.click(force=True)


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

    # 近似：y = a*price + b（最小二乗）。numpyが無ければ両端2点で近似。
    try:
        import numpy as np  # type: ignore

        P = np.array([[p, 1.0] for p, _ in pts])
        Y = np.array([y for _, y in pts])
        a, b = np.linalg.lstsq(P, Y, rcond=None)[0]

        def price_to_y(price: float) -> float:
            return float(a * price + b)

    except Exception:
        # フォールバック：最初と最後の点から直線近似
        p1, y1 = pts[0]
        p2, y2 = pts[-1]
        a = (y2 - y1) / (p2 - p1) if p2 != p1 else 0.0
        b = y1 - a * p1

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
    # オーバーレイ（overlap-manager配下など）を無効化
    with contextlib.suppress(Exception):
        await clear_overlays_aggressively(page)
        await _toggle_overlap_hidden(page, True)

    # 2) フィボナッチツールボタンを探してクリック
    # オーバーレイのポインター遮断を一時的にOFF
    try:
        await _set_overlap_pointer_events(page, True)
    except Exception:
        pass
    for i, sel in enumerate(FIB_TOOL_BUTTONS):
        try:
            if debug:
                print(f"🔍 フィボツールボタン試行 {i+1}: {sel}")

            # 要素の存在を確認
            element = page.locator(sel).first
            await element.wait_for(state="attached", timeout=1200)
            with contextlib.suppress(Exception):
                await element.scroll_into_view_if_needed(timeout=500)
            await element.wait_for(state="visible", timeout=1200)
            # 強制クリック試行 → ダメならJS clickで貫通
            try:
                await element.click(timeout=1800, force=True)
            except Exception:
                _ = await _js_force_click(page, sel, timeout_ms=1200)

            if debug:
                print("✅ フィボツールボタンクリック成功")

            # ツール選択が成功したかを確認 + Alt+F 追撃
            for _ in range(3):
                with contextlib.suppress(Exception):
                    await page.keyboard.press("Alt+F")
                await page.wait_for_timeout(120)
            if debug:
                print("🔍 フィボツール選択状態を確認...")
            with contextlib.suppress(Exception):
                await page.screenshot(
                    path="automation/screenshots/debug_fib_selected.png"
                )

            return True
        except Exception as e:
            if debug:
                print(f"❌ フィボツールボタン {i+1} 失敗: {e}")
            continue

    # 3) フォールバック：Alt+F
    if debug:
        print("🔄 Alt+Fホットキーを試行...")
    try:
        # 3-1) グループメニューから直接選択（最後の手段）
        try:
            group_sels = [
                "[data-name='linetool-group-gann-and-fibonacci']",
                "div[data-name*='gann-and-fibonacci']",
            ]
            opened = False
            for gs in group_sels:
                try:
                    if debug:
                        print(f"🧰 Gann/Fibonacci グループ開く: {gs}")
                    if not await _js_force_click(page, gs, timeout_ms=1000):
                        await page.locator(gs).first.click(timeout=1000, force=True)
                    await page.wait_for_timeout(200)
                    opened = True
                    break
                except Exception:
                    continue
            if opened:
                menu_targets = [
                    "[data-name='linetool-fib-retracement']",
                    "button[aria-label='Fib Retracement']",
                    "button[aria-label*='Fibonacci']",
                ]
                for mt in menu_targets:
                    if await _js_force_click(page, mt, timeout_ms=800):
                        if debug:
                            print("✅ グループ内からFib選択(JS)")
                        return True
                    with contextlib.suppress(Exception):
                        await page.locator(mt).first.click(timeout=800, force=True)
                        if debug:
                            print("✅ グループ内からFib選択(Click)")
                        return True
        except Exception as ee:
            if debug:
                print(f"⚠️ グループ選択フォールバック失敗: {ee}")

        # 3-2) 最後にキーバインドを数回送る（UI差異の吸収）
        for _ in range(3):
            with contextlib.suppress(Exception):
                await page.keyboard.press("Alt+F")
            await page.wait_for_timeout(120)
        if debug:
            print("✅ Alt+F多重送信完了")
        return True
    except Exception as e:
        if debug:
            print(f"❌ Alt+F失敗: {e}")
        return False
    finally:
        with contextlib.suppress(Exception):
            await _set_overlap_pointer_events(page, False)
            await _toggle_overlap_hidden(page, False)


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
    # まずポップアップを強制的に排除
    try:
        await page.add_style_tag(content=ANTI_POPUP_CSS)
        await close_popups_fast(page)
    except Exception:
        pass

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

    # フィボツール選択前にページを安定させ、キャンバスへ明示フォーカス
    await page.wait_for_timeout(400)
    # 余計なフローティングUIを閉じる
    with contextlib.suppress(Exception):
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(120)
    await _focus_plot_canvas(page)

    # オーバーレイを完全に隠してから選択
    with contextlib.suppress(Exception):
        await _toggle_overlap_hidden(page, True)
    ok = await _select_fib_tool(page, debug=True)
    if not ok:
        raise RuntimeError("Fib tool could not be selected")

    print(f"📍 フィボ描画座標: start={start}, end={end}")
    print(f"📊 価格範囲: high={high}, low={low}")

    # 描画（少しの待機を入れてからドラッグ）
    await page.wait_for_timeout(150)
    print("🖱️ マウス移動開始...")
    # キャンバス直上でのヒットを確実化するため、JSで canvas に mousedown/mousemove/mouseup を発火
    try:
        await page.evaluate(
            """
            (startX, startY, endX, endY) => {
              function fire(type, x, y) {
                const el = document.elementFromPoint(x, y);
                if (!el) return;
                const ev = new MouseEvent(type, {bubbles:true, cancelable:true, clientX:x, clientY:y});
                el.dispatchEvent(ev);
              }
              fire('mousedown', startX, startY);
              fire('mousemove', endX, endY);
              fire('mouseup', endX, endY);
            }
            """,
            start[0],
            start[1],
            end[0],
            end[1],
        )
    except Exception:
        # フォールバックに物理ドラッグ
        try:
            await _set_overlap_pointer_events(page, True)
        except Exception:
            pass
        try:
            await page.mouse.move(*start)
            await page.mouse.down()
            await page.mouse.move(*end, steps=20)
            await page.mouse.up()
        finally:
            with contextlib.suppress(Exception):
                await _set_overlap_pointer_events(page, False)

    # もし反応がなければ微妙にずらしてもう一度ドラッグ
    await page.wait_for_timeout(300)
    try:
        await page.mouse.move(start[0] + 6, start[1] + 6)
        await page.mouse.down()
        await page.mouse.move(end[0] + 6, end[1] + 6, steps=12)
        await page.mouse.up()
    except Exception:
        pass

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
    # Safeモード: 描画中は余計なCSS/ポップアップ介入を行わない（メニューが消える/遮られる対策）
    print("[safe-mode] draw_fibo_quick: skip extra CSS/close during drawing phase")

    box = await _get_plot_bbox(page)
    # オーバーレイに干渉しにくい中央寄りの広いドラッグ範囲に変更
    x1 = box["x"] + box["width"] * 0.10
    x2 = box["x"] + box["width"] * 0.90
    y_top = box["y"] + box["height"] * 0.25
    y_bot = box["y"] + box["height"] * 0.85
    start, end = (
        ((x1, y_top), (x2, y_bot))
        if direction == "high_to_low"
        else ((x1, y_bot), (x2, y_top))
    )
    # 前処理: 余計なUIを閉じてからキャンバスへフォーカス
    with contextlib.suppress(Exception):
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(120)
    await _focus_plot_canvas(page)

    ok = await _select_fib_tool(page, debug=True)
    if not ok:
        raise RuntimeError("Fib tool could not be selected")
    try:
        await page.evaluate(
            """
            (startX, startY, endX, endY) => {
              function fire(type, x, y) {
                const el = document.elementFromPoint(x, y);
                if (!el) return;
                const ev = new MouseEvent(type, {bubbles:true, cancelable:true, clientX:x, clientY:y});
                el.dispatchEvent(ev);
              }
              fire('mousedown', startX, startY);
              fire('mousemove', endX, endY);
              fire('mouseup', endX, endY);
            }
            """,
            start[0],
            start[1],
            end[0],
            end[1],
        )
    except Exception:
        with contextlib.suppress(Exception):
            await _set_overlap_pointer_events(page, True)
        try:
            await page.mouse.move(*start)
            await page.mouse.down()
            await page.mouse.move(*end, steps=20)
            await page.mouse.up()
        finally:
            with contextlib.suppress(Exception):
                await _set_overlap_pointer_events(page, False)

    # 念のため2回目の微調整ドラッグ
    await page.wait_for_timeout(250)
    with contextlib.suppress(Exception):
        await page.mouse.move(start[0] + 6, start[1] + 6)
        await page.mouse.down()
        await page.mouse.move(end[0] + 6, end[1] + 6, steps=12)
        await page.mouse.up()

    # フィボナッチ描画の安定化待機（短縮）
    print("⏳ クイックフィボ描画の安定化を待機中...")
    await page.wait_for_timeout(400)

    # ロック優先手順
    locked = False
    if await _wait_floating_toolbar(page, timeout=1200):
        with contextlib.suppress(Exception):
            locked = await _lock_last_drawing(page)
    if not locked:
        mid_x = (start[0] + end[0]) / 2.0
        mid_y = (start[1] + end[1]) / 2.0
        if await _lock_by_context_menu(page, mid_x, mid_y):
            locked = True
    if not locked:
        with contextlib.suppress(Exception):
            locked = await _lock_all_drawings_toggle(page, enable=True)
    print("🔒 ロック状態:", locked)
    await page.wait_for_timeout(400)

    # オーバーレイを元に戻す
    with contextlib.suppress(Exception):
        await _toggle_overlap_hidden(page, False)

    # デバッグ: フィボオブジェクト存在確認のためのスクショ
    with contextlib.suppress(Exception):
        await page.screenshot(path="automation/screenshots/debug_fib_after_draw.png")

    # ESCキーは使わない（フィボナッチが消去される可能性があるため）
    print("⚠️ フィボナッチ保持のためツール選択は維持...")

    return {"from": start, "to": end}


async def screenshot(page, outfile: str):
    """ポップアップを閉じてからスクショを撮る"""
    # スクショ直前の軽いクリーンのみ（強いCSS注入は避ける）
    with contextlib.suppress(Exception):
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(80)

    # 少し待機してからスクショ
    await page.wait_for_timeout(250)

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
                spec = importlib.util.spec_from_file_location("annotate", str(ap))
                if spec is None or spec.loader is None:
                    raise ImportError("failed to load annotate module spec")
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
