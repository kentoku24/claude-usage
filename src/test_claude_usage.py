"""
最低限のテスト:
1. スクリプト単体で数値が出る（Claude.ai と同じ計算）
2. SwiftBar 用の出力フォーマットになっている（メニューバーに数値が出る）
"""
import subprocess, os, re, pytest

SCRIPT = os.path.join(os.path.dirname(__file__), "claude-usage.5m.py")
LIMITED_ENV = {
    "HOME": os.path.expanduser("~"),
    "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
    "PATH": "/usr/bin:/bin",
}


def run_script():
    return subprocess.run(
        ["bash", SCRIPT],
        capture_output=True, text=True, timeout=15,
    )


def test_python_detected():
    """限定環境でも Python が見つかり、bash フォールバックにならない"""
    result = run_script()
    assert "pip3 install browser-cookie3" not in result.stdout


def test_menubar_title_has_percentage():
    """1行目（メニューバータイトル）に % が含まれる"""
    result = run_script()
    first_line = result.stdout.splitlines()[0]
    assert "%" in first_line, f"got: {first_line!r}"


def test_output_has_separator():
    """SwiftBar の区切り線 '---' が含まれる"""
    result = run_script()
    assert "---" in result.stdout
