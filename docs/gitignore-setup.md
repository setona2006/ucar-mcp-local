# .gitignore 設定ガイド - スクリーンショット除外

## 📋 概要
自動生成されるスクリーンショットやテストファイルをGitの追跡対象から除外する設定です。

## 🎯 .gitignore 更新例

### スクリーンショット除外設定
```gitignore
# === スクリーンショット・画像ファイル除外設定 ===
# automation/screenshots フォルダ配下の全てのPNG画像を無視
automation/screenshots/*.png
automation/screenshots/*.jpg
automation/screenshots/*.jpeg
automation/screenshots/*.gif

# サブフォルダがある場合も含めて除外する
automation/screenshots/**/*.png
automation/screenshots/**/*.jpg
automation/screenshots/**/*.jpeg
automation/screenshots/**/*.gif

# 作業用一時ファイル・フォルダ
automation/tmp/
automation/temp/
automation/screenshots/temp/
automation/debug/

# その他の自動生成画像ファイル
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

### テスト・デバッグファイル除外設定
```gitignore
# === テスト・デバッグ用一時ファイル ===
# テスト用JSONファイル
test_*.json
debug_*.json
temp_*.json

# 自動生成される設定ファイル
*_backup.*
*_temp.*
*.tmp
*.temp

# データベース・キャッシュファイル
*.db
*.sqlite
*.sqlite3
cache/
```

## 🔧 適用手順

### 1. .gitignore の更新
プロジェクトのルートにある `.gitignore` を開き、上記の設定を追加します。

### 2. 既存ファイルの追跡解除
すでに追跡中の `.png` ファイルは `.gitignore` に追加しただけでは除外されないので、キャッシュから削除します。

**PowerShell/ターミナルで実行:**
```bash
# スクリーンショットフォルダの全PNGファイルを追跡対象から除外
git rm --cached automation/screenshots/*.png

# 他の画像ファイルも除外する場合
git rm --cached automation/screenshots/*.jpg
git rm --cached automation/screenshots/*.gif

# テスト用JSONファイルがある場合
git rm --cached test_*.json
git rm --cached debug_*.json
```

### 3. GitHub Desktop での確認
1. **GitHub Desktop** を開く
2. **「Changes」タブ** で不要な `.png` が削除扱いになっていることを確認
3. **コミットメッセージ** を入力:
   ```
   chore: ignore generated files (screenshots, test files)
   
   - Add comprehensive .gitignore rules for generated images
   - Remove existing tracked PNG files from automation/screenshots/
   - Ignore test and debug JSON files
   ```
4. **コミット＆プッシュ** を実行

## ✅ 効果

### 今後自動的に除外されるファイル:
- ✅ `automation/screenshots/` 配下の全画像ファイル
- ✅ `test_*.json`, `debug_*.json` などのテストファイル
- ✅ `*.tmp`, `*.temp` などの一時ファイル
- ✅ キャッシュ・データベースファイル

### メリット:
- 🚀 **GitHub Desktop** に不要ファイルが表示されない
- 📦 **リポジトリサイズ** を最小化
- ⚡ **プッシュ速度** 向上
- 🧹 **クリーンな変更履歴** を維持

## 📝 注意点
- ローカルファイルは削除されません（`git rm --cached` は追跡のみ解除）
- 必要な画像ファイルがある場合は、個別に `git add -f filename.png` で強制追加可能
- サブフォルダ構造が変わった場合は、パターンを調整してください

## 🔄 メンテナンス
新しいフォルダや拡張子が増えた場合は、`.gitignore` に追加パターンを登録してください。

```gitignore
# 新しいフォルダ例
automation/new_folder/
data/exports/

# 新しい拡張子例
*.svg
*.pdf
```
