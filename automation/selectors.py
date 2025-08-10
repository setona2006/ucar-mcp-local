CHART_URL = "https://www.tradingview.com/chart/"

# シンボル検索
SEARCH_INPUT = "input[data-name='symbol-search-input'], input[aria-label='Symbol Search'], input[placeholder*='Symbol']"


# 時間足（ボタンのaria-labelが変わることがあるためホットキーfallbackも使う）
def TIMEFRAME_BUTTON(tf: str):
    # 英語UI想定のaria-label、失敗したらホットキーにフォールバック
    return f"button[aria-label='{tf}'], button[aria-label*='{tf.upper()}'], button:has-text('{tf}')"


# インジケーターボタン（多段フォールバック）
INDICATOR_BUTTONS = [
    "button[aria-label*='Indicators']",
    "button[aria-label*='Indicators & Strategies']",
    "button:has-text('Indicators')",
    "button:has-text('Indicators & Metrics')",
    "button:has-text('インジケーター')",
    "[data-name='open-indicators-dialog'] button",
]

# インジ検索入力（ダイアログ内）
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

# Fib Retracement tool (英/日/アイコン・データ属性 できるだけ多くの候補)
FIB_TOOL_BUTTONS = [
    # 具体的なデータ名/ラベル
    "button[data-name='linetool-fib-retracement']",
    "button[aria-label='Fib Retracement']",
    "button[aria-label*='Fibonacci Retracement']",
    # タイトル属性
    "button[title*='Fib']",
    "button[title*='Fibonacci']",
    # 一般的なaria-label/テキスト
    "button[aria-label*='Fib']",
    "button[aria-label*='Retracement']",
    "button:has-text('Fib')",
    "button:has-text('リトレースメント')",
    # ツールバーグループ内の候補
    "[data-name*='linetool-group'] button[aria-label*='Fib']",
    "[data-name*='drawing-toolbar'] button[aria-label*='Fib']",
    # data-name属性ベース（広め）
    "[data-name*='linetool-fib']",
    "[data-name*='fib']",
    "[data-name*='fibonacci']",
]

# プロット領域（canvasの親パネル）
PLOT_AREA = "div[data-name='pane'] canvas"
# 右側 価格軸（価格ラベル抽出に使う）
PRICE_AXIS_LABELS = (
    "div[data-name='price-axis'] span, div[data-name='price-axis'] div:has(span)"
)

# ===== Drawing object settings (floating toolbar & dialog) =====
# 浮遊ツールバーの「設定（歯車/format）」への候補
DRAWING_SETTINGS_BUTTONS = [
    "[data-name='floating-toolbar'] [data-name*='format']",
    "[data-name='floating-toolbar'] button[aria-label*='Settings']",
    "div[class*='floating-toolbar'] [data-name*='format']",
    "div[class*='floating'] button[aria-label*='Settings']",
]

# 描画オブジェクトの設定ダイアログのルート
DRAW_DIALOG = "div[role='dialog']"

# 設定のOK/Apply
DRAW_OK_BUTTON = (
    f"{DRAW_DIALOG} button:has-text('OK'), "
    f"{DRAW_DIALOG} button:has-text('Apply'), "
    f"{DRAW_DIALOG} button:has-text('適用')"
)

# ライン太さボタン（px表記の候補）
DRAW_LINEWIDTH_BUTTONS = (
    f"{DRAW_DIALOG} button[aria-label*='px'], {DRAW_DIALOG} [aria-label*='px']"
)

# ラベルON/OFFのトグル候補
DRAW_LABELS_TOGGLES = (
    f"{DRAW_DIALOG} label:has-text('Label'), " f"{DRAW_DIALOG} label:has-text('ラベル')"
)
