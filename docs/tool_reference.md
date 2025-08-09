# MCP Tools Reference

This document describes the available MCP tools, their purpose, arguments, and usage examples.

---

## 1. capture_chart
**Purpose:** Capture a screenshot of a TradingView chart.

**Arguments:**
- `symbol` *(string)* — e.g., `"USDJPY"` (instrument symbol)
- `tf` *(string)* — e.g., `"1h"` (timeframe)
- `clean` *(bool, optional)* — whether to automatically close popups/ads

**Use case:**  
- Get the current chart image for reports or analysis.

---

## 2. tv_action
**Purpose:** Perform a UI action on the TradingView interface.

**Arguments:**
- `action` *(string)* — name of the action (e.g., `"open_settings"`, `"switch_tf"`, `"toggle_indicator"`)
- `params` *(object, optional)* — extra details for the action (e.g., target timeframe)

**Use case:**  
- Toggle an indicator, change the timeframe, or perform other UI interactions.

---

## 3. tune_indicator
**Purpose:** Modify parameters of a specific indicator.

**Arguments:**
- `name` *(string)* — indicator name (e.g., `"Moving Average"`, `"MACD"`)
- `params` *(object)* — settings to apply (e.g., `{ "length": 50, "source": "close" }`)

**Use case:**  
- Customize indicator presets
- Adjust parameters for strategy testing

---

## 4. draw_fibo
**Purpose:** Automatically draw Fibonacci retracement on TradingView.

**Arguments:**
- **Price mode:**
  - `from_price` *(float)* — high price
  - `to_price` *(float)* — low price
- **Quick mode:**
  - `mode: "quick"` — auto-detect chart top/bottom
- `reverse` *(bool, optional)* — invert direction

**Use case:**  
- Save time drawing Fibonacci retracements
- Reproduce chart setups quickly

---

## 5. macro_quiettrap_report
**Purpose:** One-shot macro to apply preset → draw Fibonacci → add QuietTrap annotation → capture screenshot.

**Workflow:**
1. Open chart for given symbol/timeframe
2. Close popups/ads
3. Apply preset (default: `"senior_ma_cloud"`)
4. Draw Fibonacci (price mode or quick mode)
5. Add QuietTrap annotation
6. Save screenshot and return metadata

**Use case:**  
- Automate multi-step chart reporting
- Create annotated images for strategy reviews

---

## Summary Table

| Tool Name              | Purpose                                | Type   |
|------------------------|----------------------------------------|--------|
| capture_chart          | Chart screenshot                       | Single |
| tv_action              | TradingView UI action                  | Single |
| tune_indicator         | Indicator parameter tuning             | Single |
| draw_fibo              | Draw Fibonacci retracement             | Single |
| macro_quiettrap_report | Preset + Fibo + Annotation + Screenshot| Macro  |

---

**Note:** This document should be updated whenever new tools are added or existing tools are modified.
