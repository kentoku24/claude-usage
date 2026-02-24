#!/bin/bash
# Claude Usage SwiftBar Plugin - Setup Script

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN="$SCRIPT_DIR/claude-usage.5m.py"

echo "=== Claude Usage Setup ==="

# 1. 依存ライブラリのインストール
echo ""
echo "▶ 依存ライブラリをインストール中..."
pip3 install browser-cookie3 requests
echo "  完了 ✓"

# 2. browser_cookie3 が使える Python の絶対パスを取得してシェバンを書き換え
PYTHON=$(python3 -c "import browser_cookie3; import sys; print(sys.executable)")
echo ""
echo "▶ Python: $PYTHON"
sed -i '' "1s|.*|#!$PYTHON|" "$PLUGIN"
echo "  シェバンを更新しました ✓"

# 3. 実行権限の付与
chmod +x "$PLUGIN"
echo ""
echo "▶ 実行権限を付与しました ✓"

# 4. 動作確認
echo ""
echo "▶ 動作確認中..."
"$PYTHON" "$PLUGIN" 2>&1 | head -1

echo ""
echo "=== セットアップ完了 ==="
echo ""
echo "次のステップ:"
echo "  SwiftBar で「Refresh All」を実行してください"
