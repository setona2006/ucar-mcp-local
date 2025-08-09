# UCAR MCP Local Trading Tools

MCPブリッジ（会話→ローカル実行）とPlaywrightでTradingViewを視覚操作する最小構成です。

## ゴール
ChatGPT（UCAR）から「USDJPYの1時間足をスクショ」で、ローカルが自動でTradingViewを操作してPNGを保存。

## 0) 前提準備（初回だけ）

```bash
# Python 3.11+ 推奨
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt

# ブラウザDL
python -m playwright install
```

## 1) 環境設定

```bash
# .envファイルを作成
cp env.example .env
# .envファイルを編集してTradingViewのログイン情報を設定
```

## 2) TradingViewログイン状態の保存

最初だけヘッドフル（画面表示）でログイン → Cookie/LocalStorageをstorage_state.jsonに保存。

```bash
python automation/tv_login.py
```

※2FA利用時は、コード入力画面で手動入力してから保存でOK。以後は保存済みストレージで自動ログインになります。

## 3) 単体テスト

```bash
# USDJPY 1時間足 + RSI/Volumeのスクリーンショット
python automation/tv_controller.py
```

## 4) MCPサーバーのテスト

```bash
# 別ターミナルで起動
python mcp/mcp_server.py

# もう一方で標準入力にJSONを1行入れて試す
echo '{"id":"1","name":"capture_chart","arguments":{"symbol":"USDJPY","tf":"1h","indicators":["Relative Strength Index","Volume"],"outfile":"automation/screenshots/usdjpy_1h.png"}}' | python mcp/mcp_server.py
```

→ `automation/screenshots/usdjpy_1h.png` が保存されます。

## 5) UCAR（ChatGPT）からの呼び方（実務イメージ）

UCAR側（ChatGPT）がMCPツール`capture_chart`を呼ぶ

引数：`symbol="USDJPY"`, `tf="1h"`, `indicators=["Relative Strength Index","Volume"]`

レスポンス：`{"file":"automation/screenshots/usdjpy_1h.png"}`

そのパスの画像が回答に添付される（ChatGPTクライアント側の仕様に依存）

## よくある詰まりポイントと回避策

### ログイン弾かれる/英語UIでない
一度ヘッドフルで`tv_login.py`を実行し、手動でUI言語を英語に切り替え→保存。

2FAは手動で通した直後に`storage_state.json`保存が安定。

### セレクタ崩れ
`selectors.py`で集約し、壊れたらここだけ直す。

検索ホットキー（`/`）、時間足ホットキー（数字＋Enter）を多用すると安定。

### Cloudflare等のBot対策
初回は`headless=False`で数秒待機を入れると通りやすい。

ローカルIPを固定。VPNはなるべく安定回線。

### 遅すぎる/要素が見つからない
`wait_for_timeout(...)`を適度に入れる。

`wait_for_load_state("networkidle")`を明示。

### 画像が暗い/余白が多い
スクショ前に「F11」相当で全画面、または`page.locator("canvas")`等で範囲スクショへ拡張。

## プロジェクト構成

```
ucar-mcp-local/
├─ env.example          # 環境変数テンプレート
├─ requirements.txt     # Python依存関係
├─ README.md           # このファイル
├─ mcp/
│  ├─ manifest.json    # MCPツール定義
│  └─ mcp_server.py    # MCPサーバー（stdin/stdout）
└─ automation/
   ├─ tv_controller.py # メインコントローラー
   ├─ tv_login.py      # ログイン処理
   ├─ selectors.py     # UI要素セレクタ
   └─ screenshots/     # スクリーンショット保存先
```
