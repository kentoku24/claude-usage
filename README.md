# Codex Usage Menu Bar Widget

Codex の使用量を Mac のメニューバーにリアルタイム表示する SwiftBar プラグイン。
探して見つからなかったので自作したが、 https://github.com/steipete/CodexBar というOSSがすでにあった。

## 表示内容

```
🟡 5h:18%  🟢 Weekly:41%
```

クリックで展開：

```
🟡 5h usage: 18%
   ██░░░░░░░░░░ 18%
   📈 5h予測: 83%
   🔄 3時間57分後にリセット
---
🟢 Weekly usage: 41%
   █████░░░░░░░ 41%
   📈 7d予測: 49%
   🔄 水 20:59 にリセット
---
↗ chatgpt.com/codex/settings/usage
↺ 今すぐ更新
```

### アイコンの意味

| アイコン | 条件 |
|--------|------|
| 🟢 | ウィンドウ終了時の予測使用率 < 80% |
| 🟡 | ウィンドウ終了時の予測使用率 ≥ 80% |
| 🔴 | ウィンドウ終了時の予測使用率 ≥ 100%（オーバー） |

メニューバー左端のアイコンは、全指標のうち**最も悪い予測**を表示します。

## セットアップ

### 1. SwiftBar をインストール

```bash
brew install --cask swiftbar
```

または [swiftbar.app](https://swiftbar.app) からダウンロード。

### 2. データ取得方式を選ぶ

2つのデータ取得方式があります：

| 方式 | 設定値 | 依存 | 認証 |
|------|--------|------|------|
| **browser** | `"browser"` | `browser-cookie3` + `requests` | Chrome/Safari/Firefox の Cookie（OpenAI ダッシュボード） |
| **oauth** | `"oauth"` | `requests` のみ | `~/.codex/auth.json` の OAuth トークン |

**oauth モード**（デフォルト）: Codex にログイン済みで `~/.codex/auth.json` があれば追加設定不要。`browser-cookie3` も不要。

```bash
pip3 install requests
```

**browser モード**: OpenAI ダッシュボードの Cookie から usage ページを読む代替手段です。`auth.json` がない場合の保険として使ってください。

```bash
pip3 install browser-cookie3 requests
```

`~/.codex-usage-config.json` で方式を切り替えられます：

```json
{"data_source": "oauth"}
```

> **重要**: SwiftBar は独自の環境でスクリプトを実行するため、shebang に Python の絶対パスを指定する必要があります。

どの python3 を使っているか確認：

```bash
which python3
```

`claude-usage.5m.py` の1行目を実際のパスに書き換えます：

```python
#!/usr/bin/env python3   # デフォルト（PATHが通っている場合）
# または
#!/Users/yourname/.local/share/mise/installs/python/3.14.3/bin/python3  # mise 使用時
# または
#!/opt/homebrew/bin/python3  # Homebrew で直接インストール時
```

mise を使っている場合は以下で確認できます：

```bash
mise which python3
```

### 3. プラグインフォルダを作成してスクリプトを配置

```bash
# プラグインフォルダを作成（場所は自由）
mkdir -p ~/Documents/SwiftBar

# スクリプトをコピー
cp src/claude-usage.5m.py ~/Documents/SwiftBar/

# 実行権限を付与
chmod +x ~/Documents/SwiftBar/claude-usage.5m.py

# 設定ファイルを作成（お好みで編集）
cat > ~/.codex-usage-config.json <<'JSON'
{"data_source":"oauth"}
JSON
```

### 4. SwiftBar を起動してフォルダを選択

1. SwiftBar を起動
2. プラグインフォルダの選択ダイアログが表示されたら `~/Documents/SwiftBar` を選択
3. メニューバーに Codex の使用量が表示されれば完了

### 5. 動作確認

**ステップ1: スクリプト単体で動作確認**

```bash
bash /path/to/src/claude-usage.5m.py
```

`%` を含む出力が出れば正常。`pip3 install...` と出た場合は Python 検出の問題。

**ステップ2: SwiftBar を更新**

メニューバーの SwiftBar アイコン → **Refresh All**

**ステップ3: それでも表示されない場合は再起動**

SwiftBar 自体の Glitch でメニューバーアイテムが消えることがあります（スクリプトが正常でも起きます）。

```bash
pkill -x SwiftBar && open -a SwiftBar
```

> スクリプト単体（ステップ1）で正常出力が出ているのにメニューバーに出ない場合は SwiftBar の再起動で解消します。

## トラブルシューティング

### `依存ライブラリ不足: browser_cookie3`（browser モード）

SwiftBar が別の Python を使っています。shebang を `browser_cookie3` がインストールされている Python の絶対パスに変更してください。

```bash
# browser_cookie3 がある Python を探す
python3 -c "import browser_cookie3; import sys; print(sys.executable)"
```

出力されたパスを shebang に設定します。

または、oauth モードに切り替えれば `browser-cookie3` は不要です：

```json
{"data_source": "oauth"}
```

### 認証エラー（401 / 403）

**browser モード**: OpenAI ダッシュボードにログインしているか確認してください。ブラウザで一度 `https://chatgpt.com/codex/settings/usage` を開いてから再試行。

**oauth モード**: `~/.codex/auth.json` の access token が期限切れです。Codex に再ログインしてください。

### ネット切断時

- 📵 Codex（グレー）→ オフライン
- ⏳ Codex（グレー）→ タイムアウト（再試行ボタンあり）

## カスタマイズ

### 設定ファイル（`~/.codex-usage-config.json`）

以下の設定ファイルを作成することで動作をカスタマイズできます。ファイルがない場合はデフォルト値が使われます。

```json
{
  "data_source": "oauth",
  "warn_pct":  80,
  "alert_pct": 100,
  "bar_width": 12,
  "metrics": ["primary_window", "secondary_window"]
}
```

| キー | デフォルト | 説明 |
|-----|-----------|------|
| `data_source` | `"oauth"` | データ取得方式（`"oauth"` or `"browser"`） |
| `warn_pct` | `80` | 警告通知を送る予測使用率の閾値（🟡） |
| `alert_pct` | `100` | アラート通知を送る予測使用率の閾値（🔴） |
| `bar_width` | `12` | プログレスバーの文字数 |
| `metrics` | 全指標 | 表示する指標のリスト（順序も反映） |

**設定例**: 5h 枠だけ表示、70% 超で警告

```json
{
  "warn_pct": 70,
  "metrics": ["primary_window"]
}
```

### macOS 通知アラート

予測使用率が `warn_pct`（デフォルト 80%）または `alert_pct`（デフォルト 100%）を超えると、macOS の通知センターに通知が届きます。

- 同じリセットサイクル内で各閾値につき **1回のみ** 送信されます（連続通知なし）
- リセット後は自動的にリセットされます
- 通知の状態は `~/.codex-usage-alerted.json` で管理されます

### 更新頻度のカスタマイズ

ファイル名の `5m` が更新間隔です。変更する場合はファイルをリネームします：

```bash
# 1分ごとに更新
mv ~/Documents/SwiftBar/claude-usage.5m.py ~/Documents/SwiftBar/claude-usage.1m.py

# 10分ごとに更新
mv ~/Documents/SwiftBar/claude-usage.5m.py ~/Documents/SwiftBar/claude-usage.10m.py
```

## テスト

```bash
python3 -m pytest test_claude_usage.py -v
```

| テスト | 検証内容 |
|--------|---------|
| `test_python_detected` | SwiftBar相当の限定環境でPythonが見つかる |
| `test_menubar_title_has_percentage` | 1行目に `%` が含まれる（数値表示） |
| `test_output_has_separator` | SwiftBarフォーマット `---` が含まれる |

> Codex にアクセスできる環境（`~/.codex/auth.json` または OpenAI ダッシュボード Cookie）が必要です。

## 仕組み

JSON API を直接叩いて使用量データを取得します（HTML スクレイピングではないため、UI 変更の影響を受けません）。

| 方式 | エンドポイント |
|------|--------------|
| browser | `chatgpt.com/codex/settings/usage`（Cookie から HTML を抽出） |
| oauth | `chatgpt.com/backend-api/wham/usage`（Codex auth.json の OAuth トークン） |

取得するデータ：

| キー | 意味 | ウィンドウ |
|-----|------|---------|
| `five_hour` | 現在のセッション使用量 | 5時間 |
| `seven_day` | 全モデルの使用量 | 7日間 |
| `seven_day_sonnet` | Sonnet のみの使用量 | 7日間 |
