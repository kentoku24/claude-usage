# Claude Usage Menu Bar Widget

Claude.ai の使用量（セッション / 全モデル / Sonnet）を Mac のメニューバーにリアルタイム表示する SwiftBar プラグイン。

## 表示内容

```
🟡 Session:18%  All:41%  Sonnet:28%
```

クリックで展開：

```
🟡 現在のセッション: 18%
   ██░░░░░░░░░░ 18%
   📈 5h予測: 83%
   🔄 3時間57分後にリセット
---
🟢 すべてのモデル: 41%
   █████░░░░░░░ 41%
   📈 7d予測: 49%
   🔄 水 20:59 にリセット
---
🟢 Sonnet のみ: 28%
   ███░░░░░░░░░ 28%
   📈 7d予測: 31%
   🔄 14時間57分後にリセット
---
↗ claude.ai/settings/usage
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

### 2. 依存ライブラリをインストール

```bash
pip3 install browser-cookie3 requests
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

# 設定ファイルをコピー（お好みで編集）
cp config.example.json ~/.claude-usage-config.json
```

### 4. SwiftBar を起動してフォルダを選択

1. SwiftBar を起動
2. プラグインフォルダの選択ダイアログが表示されたら `~/Documents/SwiftBar` を選択
3. メニューバーに Claude の使用量が表示されれば完了

### 5. 動作確認

SwiftBar アイコン → **Refresh All** で更新。

表示されない場合はターミナルで直接実行して確認：

```bash
# SwiftBar と同じ環境変数をセットして実行
export SWIFTBAR=1
python3 ~/Documents/SwiftBar/claude-usage.5m.py
```

## トラブルシューティング

### `依存ライブラリ不足: browser_cookie3`

SwiftBar が別の Python を使っています。shebang を `browser_cookie3` がインストールされている Python の絶対パスに変更してください。

```bash
# browser_cookie3 がある Python を探す
python3 -c "import browser_cookie3; import sys; print(sys.executable)"
```

出力されたパスを shebang に設定します。

### `エラー: Keychain access failed` などの認証エラー

Chrome で claude.ai にログインしているか確認してください。ブラウザで一度 `claude.ai/settings/usage` を開いてから再試行してください。

### ネット切断時

- 📵 Claude（グレー）→ オフライン
- ⏳ Claude（グレー）→ タイムアウト（再試行ボタンあり）

## カスタマイズ

### 設定ファイル（`~/.claude-usage-config.json`）

以下の設定ファイルを作成することで動作をカスタマイズできます。ファイルがない場合はデフォルト値が使われます。

```json
{
  "warn_pct":  80,
  "alert_pct": 100,
  "bar_width": 12,
  "metrics": ["five_hour", "seven_day", "seven_day_sonnet"]
}
```

| キー | デフォルト | 説明 |
|-----|-----------|------|
| `warn_pct` | `80` | 警告通知を送る予測使用率の閾値（🟡） |
| `alert_pct` | `100` | アラート通知を送る予測使用率の閾値（🔴） |
| `bar_width` | `12` | プログレスバーの文字数 |
| `metrics` | 全3指標 | 表示する指標のリスト（順序も反映） |

**設定例**: Sonnet だけ表示、70% 超で警告

```json
{
  "warn_pct": 70,
  "metrics": ["seven_day_sonnet"]
}
```

### macOS 通知アラート

予測使用率が `warn_pct`（デフォルト 80%）または `alert_pct`（デフォルト 100%）を超えると、macOS の通知センターに通知が届きます。

- 同じリセットサイクル内で各閾値につき **1回のみ** 送信されます（連続通知なし）
- リセット後は自動的にリセットされます
- 通知の状態は `~/.claude-usage-alerted.json` で管理されます

### 更新頻度のカスタマイズ

ファイル名の `5m` が更新間隔です。変更する場合はファイルをリネームします：

```bash
# 1分ごとに更新
mv ~/Documents/SwiftBar/claude-usage.5m.py ~/Documents/SwiftBar/claude-usage.1m.py

# 10分ごとに更新
mv ~/Documents/SwiftBar/claude-usage.5m.py ~/Documents/SwiftBar/claude-usage.10m.py
```

## 仕組み

Chrome の Cookie を使って `claude.ai/api/organizations/{uuid}/usage` という JSON エンドポイントを直接叩いています。HTML スクレイピングではないため、UI が変わっても動作します。

取得するデータ：

| キー | 意味 | ウィンドウ |
|-----|------|---------|
| `five_hour` | 現在のセッション使用量 | 5時間 |
| `seven_day` | 全モデルの使用量 | 7日間 |
| `seven_day_sonnet` | Sonnet のみの使用量 | 7日間 |
