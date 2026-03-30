"""
最低限のテスト:
1. スクリプト単体で数値が出る（Claude.ai と同じ計算）
2. SwiftBar 用の出力フォーマットになっている（メニューバーに数値が出る）
"""
import importlib.util
import json
import os
import subprocess
import sys

import pytest

SCRIPT = os.path.join(os.path.dirname(__file__), "src", "claude-usage.5m.py")
LIMITED_ENV = {
    "HOME": os.path.expanduser("~"),
    "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
    "PATH": "/usr/bin:/bin",
}


def load_module():
    module_name = "claude_usage_5m_test_module"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def run_script():
    return subprocess.run(
        ["bash", SCRIPT],
        capture_output=True, text=True, timeout=15,
    )


def test_python_detected():
    """限定環境でも Python が見つかり、bash フォールバックにならない"""
    result = run_script()
    # bash polyglot フォールバック時のエラーメッセージが出ていないことを確認
    assert "pip3 install requests" not in result.stdout


def test_menubar_title_has_percentage():
    """1行目（メニューバータイトル）に % が含まれる"""
    result = run_script()
    first_line = result.stdout.splitlines()[0]
    assert "%" in first_line, f"got: {first_line!r}"


def test_output_has_separator():
    """SwiftBar の区切り線 '---' が含まれる"""
    result = run_script()
    assert "---" in result.stdout


def test_load_config_prefers_provider_over_legacy_data_source(tmp_path, monkeypatch):
    module = load_module()
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"provider": "claude", "data_source": "oauth"}))
    monkeypatch.setattr(module, "CONFIG_PATHS", [config_path], raising=False)

    config = module.load_config()

    assert config["provider"] == "claude"


@pytest.mark.parametrize("legacy_value", ["oauth", "browser"])
def test_load_config_maps_legacy_data_source_to_codex_provider(tmp_path, monkeypatch, legacy_value):
    module = load_module()
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"data_source": legacy_value}))
    monkeypatch.setattr(module, "CONFIG_PATHS", [config_path], raising=False)

    config = module.load_config()

    assert config["provider"] == "codex"


def test_load_config_rejects_invalid_provider(tmp_path, monkeypatch):
    module = load_module()
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"provider": "nope"}))
    monkeypatch.setattr(module, "CONFIG_PATHS", [config_path], raising=False)

    with pytest.raises(RuntimeError, match="unsupported provider: nope"):
        module.load_config()


def test_load_cache_rejects_legacy_cache_provider_mismatch(tmp_path, monkeypatch):
    module = load_module()
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(json.dumps({
        "cache_schema_version": 2,
        "cache_source": "local_history",
        "provider": "claude",
        "result": {
            "status": "ok",
            "reason": "",
            "snapshot_time": "2026-03-30T12:00:00+00:00",
            "source_path": "/tmp/claude.jsonl",
            "cacheable": True,
            "items": [{"key": "primary_window", "pct": 18}],
        },
    }))
    monkeypatch.setattr(module, "CACHE_PATHS", [cache_path], raising=False)

    assert module.load_cache("codex") is None


def test_load_cache_rejects_non_local_history_entries(tmp_path, monkeypatch):
    module = load_module()
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(json.dumps({
        "cache_schema_version": 2,
        "cache_source": "oauth",
        "provider": "codex",
        "result": {
            "status": "ok",
            "reason": "",
            "snapshot_time": "2026-03-30T12:00:00+00:00",
            "source_path": "/tmp/codex.jsonl",
            "cacheable": True,
            "items": [{"key": "primary_window", "pct": 18}],
        },
    }))
    monkeypatch.setattr(module, "CACHE_PATHS", [cache_path], raising=False)

    assert module.load_cache("codex") is None


def test_save_cache_defaults_to_non_local_history_provenance(tmp_path, monkeypatch):
    module = load_module()
    cache_path = tmp_path / "cache.json"
    monkeypatch.setattr(module, "CACHE_PATHS", [cache_path], raising=False)

    module.save_cache("codex", {
        "status": "ok",
        "reason": "",
        "snapshot_time": None,
        "source_path": None,
        "cacheable": True,
        "items": [{"key": "primary_window", "pct": 18}],
    })

    payload = json.loads(cache_path.read_text())

    assert payload["cache_source"] != "local_history"
    assert module.load_cache("codex") is None


def test_main_renders_invalid_provider_config_error(monkeypatch, capsys):
    module = load_module()
    monkeypatch.setattr(module, "load_config", lambda: {
        "provider": "nope",
        "caution_pct": 60,
        "warn_pct": 80,
        "alert_pct": 100,
        "bar_width": 12,
        "metrics": [],
    })
    monkeypatch.setattr(module, "load_cache", lambda provider: pytest.fail("load_cache should not be called"))
    monkeypatch.setattr(module, "fetch_usage_oauth", lambda: pytest.fail("fetch_usage_oauth should not be called"))
    monkeypatch.setattr(module, "fetch_usage_browser", lambda: pytest.fail("fetch_usage_browser should not be called"))

    module.main()

    captured = capsys.readouterr()
    assert "unsupported provider: nope" in captured.out


def test_main_rejects_claude_provider_before_legacy_fetch(monkeypatch, capsys):
    module = load_module()
    monkeypatch.setattr(module, "load_config", lambda: {
        "provider": "claude",
        "data_source": "oauth",
        "caution_pct": 60,
        "warn_pct": 80,
        "alert_pct": 100,
        "bar_width": 12,
        "metrics": [],
    })
    monkeypatch.setattr(module, "load_cache", lambda provider: pytest.fail("load_cache should not be called"))
    monkeypatch.setattr(module, "fetch_usage_oauth", lambda: pytest.fail("fetch_usage_oauth should not be called"))
    monkeypatch.setattr(module, "fetch_usage_browser", lambda: pytest.fail("fetch_usage_browser should not be called"))

    module.main()

    captured = capsys.readouterr()
    assert "provider not yet supported: claude" in captured.out
