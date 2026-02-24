#!/bin/bash
# Claude Usage SwiftBar Plugin - Setup Script

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN="$SCRIPT_DIR/claude-usage.5m.py"

echo "=== Claude Usage Setup ==="

# 依存ライブラリのインストール
echo ""
echo "▶ 依存ライブラリをインストール中..."
pip3 install browser-cookie3 requests
echo "  完了 ✓"

# 実行権限の付与
chmod +x "$PLUGIN"
echo ""
echo "▶ 実行権限を付与しました ✓"

# 動作確認
echo ""
echo "▶ 動作確認中..."
python3 "$PLUGIN" 2>&1 | head -1

echo ""
echo "=== セットアップ完了 ==="
echo ""
echo "次のステップ:"
echo "  $PLUGIN を SwiftBar のプラグインフォルダにコピーしてください"
