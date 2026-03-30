# Claude Usage Menu Bar Widget

SwiftBar で `codex` / `claude` の利用率をメニューバー表示するプラグインです。

このリポジトリは local-history-only です。クレデンシャル、Cookie、Keychain、外部 API にはアクセスしません。

## 現在の対応状況

- `provider: "codex"`: 対応済み
  - `~/.codex/sessions/**/*.jsonl`
  - `~/.codex/archived_sessions/*.jsonl`
  - 最新の `token_count.rate_limits` snapshot を使って表示します
- `provider: "claude"`: Phase 1
  - `~/.claude/projects/**/*.jsonl`
  - `~/.claude/history.jsonl`
  - 明示的な `%` と absolute reset timestamp が同じ local history に見つからない限り `unavailable` を返します

## 特徴

- ローカル履歴だけを読みます
- provider ごとに cache を分離します
- fresh な local history があればその値を表示します
- local history が読めない、古い、見つからない場合は local-history-specific な fallback を表示します

## セットアップ

### 1. SwiftBar をインストール

```bash
brew install --cask swiftbar
```

### 2. プラグインを配置

```bash
mkdir -p ~/Documents/SwiftBar
cp src/claude-usage.5m.py ~/Documents/SwiftBar/
chmod +x ~/Documents/SwiftBar/claude-usage.5m.py
cp config.example.json ~/.claude-usage-config.json
```

### 3. SwiftBar でフォルダを選択

`~/Documents/SwiftBar` を選ぶと、5 分ごとに widget が更新されます。

## 設定

`~/.claude-usage-config.json`

```json
{
  "provider": "codex",
  "caution_pct": 60,
  "warn_pct": 80,
  "alert_pct": 100,
  "bar_width": 12,
  "metrics": []
}
```

設定項目:

- `provider`: `codex` または `claude`
- `caution_pct`: 注意表示の閾値
- `warn_pct`: 通知の警告閾値
- `alert_pct`: 通知の上限超過閾値
- `bar_width`: プログレスバー幅
- `metrics`: 互換用フィールド。local history provider の表示では現状必須ではありません

互換性:

- 旧 `data_source` は deprecated ですが読み込みます
- `"oauth"` / `"browser"` はどちらも provider `codex` として扱います

## 期待される挙動

- Codex の local history があれば `%` が表示されます
- local history がまだ無ければ `missing` / `unavailable` 系のメッセージが出ます
- 初回や履歴がまだ生成されていない状態で空表示になるのは正常です

## トラブルシューティング

### ローカル履歴が見つからない

- Codex を実際に使って `~/.codex/sessions` に履歴ができるか確認してください
- Claude は Phase 1 のため、明示的な quota snapshot が無ければ unavailable のままです

### ローカル履歴が読めない

- history ファイルの権限や破損を確認してください
- unreadable の場合は provider-scoped cache があればそちらを stale 表示します

### 表示が古い

- すべての window が過去 reset になっている snapshot は stale 扱いです
- stale 表示時は通知を抑止します

## テスト

```bash
uv run --with pytest python -m pytest test_claude_usage.py -v
```

## 実装メモ

- remote fetch は削除済みです
- 標準ライブラリだけで動作します
- SwiftBar wrapper は Python 3.10+ のみを要求します
