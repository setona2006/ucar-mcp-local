# `.gitignore` 完全ガイド（UCAR MCP Local）

このドキュメントは、プロジェクトで **Gitに入れないファイルを管理する方法** を、初心者でも迷わないようにまとめたものです。  
「なぜ無視（ignore）するのか／何を無視すべきか／後から追加・変更する方法」まで一通りカバーします。

---

## 1. `.gitignore` は何をする？（超要約）
- Git が **履歴に入れようとするファイル** のうち、不要なものを **最初から見なかったことにする** フィルタ。
- 例：スクリーンショット、ログ、キャッシュ、個人設定（.env など）は入れない。

> 例え：**倉庫の入り口にある仕分け係**。「この段ボールは入れないでね」と伝えるリストが `.gitignore`。

---

## 2. 今回プロジェクトの主な除外方針
- **自動生成物**（スクショ、レポート、キャッシュ、ログ）はコミットしない  
- **個人依存ファイル**（.env、ローカル設定、IDE設定）はコミットしない  
- **大容量 or 無意味な差分**（画像、バイナリ）は極力コミットしない  

---

## 3. 現在の `.gitignore` の主なルール（抜粋解説）

### 3.1 スクリーンショット・画像系
```gitignore
# automation/screenshots 配下の画像を全部無視
automation/screenshots/*.png
automation/screenshots/**/*.png
automation/screenshots/*.jpg
automation/screenshots/**/*.jpg
automation/screenshots/*.jpeg
automation/screenshots/**/*.jpeg
automation/screenshots/*.gif
automation/screenshots/**/*.gif

# その他の自動生成画像（安全側の保険）
charts/
reports/
output/
*.png
*.jpg
*.jpeg
*.gif
*.bmp
*.tiff
*.webp
```
- **ポイント**：`**/*` はサブフォルダも含めて無視します。  
- 画像は差分が見えない & 容量が増えるので、成果物は**必要なときにだけ配布**（GitHub Releases や添付）推奨。

### 3.2 Playwright や一時ファイル
```gitignore
automation/storage_state.json    # TradingViewログインセッション
playwright-report/
test-results/
automation/tmp/
automation/temp/
automation/screenshots/temp/
automation/debug/
```
- **セッション情報**は秘匿情報なので必ず除外。  
- テストの一時フォルダやレポートも除外。

### 3.3 開発環境・個人設定
```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.eggs/

# 仮想環境
.venv/
env/
venv/

# IDE
.vscode/
.cursor/
.idea/
*.iml

# 環境変数
.env
.env.*
```
- `.env` は APIキーやパスワードが入る可能性あり → 絶対コミットしない。

### 3.4 OS・その他
```gitignore
.DS_Store
Thumbs.db
*.log
logs/
cache/
*.db
*.sqlite*
*_backup.*
*_temp.*
*.tmp
*.temp
```
- OSのゴミ（.DS_Store, Thumbs.db）や一時ファイルを横断的に除外。

---

## 4. すでに追跡されてしまったファイルを外すには？（超重要）
`.gitignore` に書いただけでは、**すでにGitが追跡しているファイル** は外れません。  
一度「キャッシュから外す」操作が必要です。

```bash
# 例：スクショPNGを一括で追跡解除（ローカルの実体ファイルは残る）
git rm --cached automation/screenshots/*.png
git rm --cached automation/screenshots/**/*.png

# 画像全般を外す（慎重に！）
git rm --cached *.png *.jpg *.jpeg *.gif
```

その後、**コミット＆プッシュ** でリポジトリから削除（履歴からは消えませんが、以後は追跡されません）。

> 💡 `--cached` を付ければ **ローカルのファイルは消えず**、Gitの管理から外すだけです。

---

## 5. GitHub Desktop での確認手順
1. `.gitignore` を更新する（保存）  
2. GitHub Desktop の **Changes** タブを開く  
3. 追跡中だった不要ファイルが **「削除扱い」** で表示される  
4. コミットメッセージをつけて **Commit to main**  
5. **Push origin** で反映

> 以後、同じ種類のファイルは「Changes」に出てこなくなります。

---

## 6. 新しい除外を追加するときのコツ（パターン早見表）
| 目的 | 例 | ルール |
|-----|----|-------|
| フォルダごと除外 | `automation/debug/` | `automation/debug/` |
| そのフォルダ直下のPNGのみ | `automation/screenshots/*.png` | `automation/screenshots/*.png` |
| サブフォルダも含むPNG | `automation/screenshots/**/*.png` | `automation/screenshots/**/*.png` |
| 拡張子で一括除外 | すべてのJPEG | `*.jpg` / `*.jpeg` |
| 一時ファイルの共通パターン | `_temp`, `.tmp` など | `*_temp.*`, `*.tmp` |
| 秘密鍵や環境変数 | `.env`, `*.pem` | `.env`, `*.pem` |

> **順番**：基本的に上から評価されます。後のルールで上書きしたい場合は順序を考慮してください。  
> **例外指定**（無視から除外したい）は `!` を使います（例：`!docs/keep.png`）。

---

## 7. よくある落とし穴
- `.gitignore` に追加したのに効かない → **すでに追跡済み**（→ 4章の `git rm --cached`）。  
- サブフォルダのファイルが除外されない → `**/*` を使っていない。  
- スクリーンショットを共有したい → **Gitに入れず**、必要なときだけ **Releaseやクラウドストレージ** で配布。  
- 機密を誤コミットした → 早めに **履歴から削除（BFG Repo-Cleaner / git filter-repo）** を検討。

---

## 8. 運用・メンテの型
- ルールを増やすときは **まずローカルで試す**（`git status` で意図通りか確認）。  
- 共有したい生成物は **`docs/`** など専用ディレクトリに置きつつ、サイズに注意（Git LFS も検討）。  
- `README` に **成果物の作り方**（例：GIFの生成手順）を残す。生成物そのものは極力コミットしない。  
- 定期的に `.gitignore` を見直し、**新しい自動生成物やツール導入**に合わせて更新。

---

## 9. トラブル対処のミニ手順
1. 「Changes にゴミが出続ける」→ `.gitignore` にパターン追加  
2. 「それでも出る」→ `git rm --cached path/to/file` で追跡解除  
3. 「消したくない」→ `--cached` を付ければローカルは残る  
4. 「プッシュ済みを消したい」→ PRで削除し、以後 `.gitignore` で再発防止

---

## 10. チェックリスト（コミット前）
- [ ] `.env` や `storage_state.json` をコミットしていない  
- [ ] `automation/screenshots/` 配下が Changes に出ていない  
- [ ] ローカル専用の一時フォルダ（`temp/`, `debug/`）をコミットしていない  
- [ ] 画像や生成物は必要最小限のみ（原則コミットしない）  

---

## 付録：このプロジェクトで特に重要な除外（再掲）
```gitignore
# セッション・機密
.env
.env.*
automation/storage_state.json

# 画像・生成物
automation/screenshots/**
charts/
reports/
output/
*.png *.jpg *.jpeg *.gif *.bmp *.tiff *.webp

# 一時・ゴミ
__pycache__/
.venv/
logs/
cache/
*.tmp *.temp
.DS_Store
Thumbs.db
```
この方針を守れば、**GitHub Desktopが常にクリーン**に保てます。

