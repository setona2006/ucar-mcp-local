# UCAR MCP Local

ローカル環境でGPTアプリやMCP経由からTradingViewを操作する自動化ツール集。

## 概要

- **Playwright + Python** によるTradingViewの視覚操作
- **MCP Server** として動作し、ツール呼び出しに応じて各種操作を実行
- **macro_quiettrap_report** により
  - プリセット適用
  - フィボナッチ描画（価格指定 or クイック）
  - QuietTrap注釈付きスクリーンショット
  を1コマンドで実行可能

## セットアップ

```bash
git clone https://github.com/<yourname>/ucar-mcp-local.git
cd ucar-mcp-local
python -m venv .venv
source .venv/bin/activate  # Windowsは .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### 初回設定

1. `.env`ファイルを作成し、TradingViewログイン情報を設定：
```bash
cp .env.example .env
# .envファイルを編集してログイン情報を入力
```

2. 初回ログインでセッション保存：
```bash
python automation/tv_login.py
```

## 使用例

### 価格指定バージョン：

```bash
echo '{
  "id":"mq1",
  "name":"macro_quiettrap_report",
  "arguments":{
    "symbol":"USDJPY","tf":"1h",
    "preset_name":"senior_ma_cloud","clear_existing":true,
    "draw_fibo": true, "fibo_mode":"prices",
    "high":148.96, "low":147.10,
    "quiettrap":{"side":"sell","score":0.86,"notes":["fibo 148.96→147.10"]}
  }
}' | python mcp/mcp_server.py
```

### クイック版：

```bash
echo '{
  "id":"mq2",
  "name":"macro_quiettrap_report",
  "arguments":{
    "symbol":"USDJPY","tf":"1h",
    "preset_name":"senior_ma_cloud",
    "draw_fibo": true, "fibo_mode":"quick",
    "quiettrap":{"side":"sell","score":0.73,"notes":["quick fib"]}
  }
}' | python mcp/mcp_server.py
```

### 高速モード（パラメータ調整スキップ）：

```bash
echo '{
  "id":"mq3",
  "name":"macro_quiettrap_report",
  "arguments":{
    "symbol":"USDJPY","tf":"1h",
    "preset_name":"senior_ma_cloud",
    "skip_params": true,
    "draw_fibo": true, "fibo_mode":"prices",
    "high":148.96, "low":147.10,
    "quiettrap":{"side":"sell","score":0.86,"notes":["fast mode"]}
  }
}' | python mcp/mcp_server.py
```

## 主要機能

### MCPツール一覧

1. **`capture_chart`** - チャートスクリーンショット撮影
2. **`tv_action`** - TradingView UI操作
3. **`tune_indicator`** - インジケーター設定調整
4. **`draw_fibo`** - フィボナッチリトレースメント描画
5. **`macro_quiettrap_report`** - 一撃マクロ（プリセット→フィボ→注釈→スクショ）

### プリセット

- `senior_ma_cloud`: MA20/MA75/EMA200の基本構成
- `rsi_vol_ma200`: RSI(14) + Volume + SMA(200)
- `ema50_200_rsi_macd`: EMA(50/200) + RSI(14) + MACD
- `scalp_light`: スキャルピング軽量（RSI + Volume）

## 開発

### テスト実行

```bash
# CIと同様のスモークテスト
echo '{"id":"t1","name":"capture_chart","arguments":{"symbol":"USDJPY","tf":"1h"}}' | python mcp/mcp_server.py
```

### ファイル構成

```
ucar-mcp-local/
├── .github/workflows/ci.yml    # GitHub Actions CI
├── mcp/
│   ├── manifest.json           # MCPツール定義
│   └── mcp_server.py           # MCPサーバー本体
├── automation/
│   ├── tv_controller.py        # TradingView操作ロジック
│   ├── selectors.py            # UIセレクタ定義
│   ├── annotate.py             # QuietTrap注釈機能
│   ├── indicators.json         # インジケータープリセット
│   └── tv_login.py             # 初回ログイン用
├── .env.example                # 環境変数テンプレート
├── requirements.txt            # Python依存関係
└── README.md                   # このファイル
```

## ライセンス

MIT License

## 貢献

1. Fork this repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## サポート

問題や質問がある場合は、GitHubのIssuesをご利用ください。