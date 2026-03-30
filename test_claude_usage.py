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
from pathlib import Path

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


def fixture_path(name: str) -> Path:
    return Path(__file__).parent / "tests" / "fixtures" / name


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


def test_load_cache_rejects_local_history_entries_without_items_list(tmp_path, monkeypatch):
    module = load_module()
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(json.dumps({
        "cache_schema_version": 2,
        "cache_source": "local_history",
        "provider": "codex",
        "result": {
            "status": "ok",
            "reason": "",
            "snapshot_time": "2026-03-30T12:00:00+00:00",
            "source_path": "/tmp/codex.jsonl",
            "cacheable": True,
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

    module.main()

    captured = capsys.readouterr()
    assert "unsupported provider: nope" in captured.out


def test_load_usage_items_dispatches_codex_provider(monkeypatch):
    module = load_module()
    expected = module.make_provider_result(
        "ok",
        snapshot_time="2030-01-01T00:00:00+00:00",
        source_path="/tmp/codex.jsonl",
        cacheable=True,
        items=[],
    )
    monkeypatch.setattr(module, "load_codex_history_items", lambda: expected)

    result = module.load_usage_items("codex", {"provider": "codex"})

    assert result == expected


def test_load_usage_items_returns_unavailable_for_claude_provider():
    module = load_module()

    result = module.load_usage_items("claude", {"provider": "claude"})

    assert result["status"] == "unavailable"
    assert result["cacheable"] is False
    assert result["items"] == []
    assert "not wired yet" in result["reason"]


def test_load_usage_items_rejects_unsupported_provider():
    module = load_module()

    with pytest.raises(RuntimeError, match="unsupported provider: nope"):
        module.load_usage_items("nope", {"provider": "nope"})


def test_main_uses_codex_provider_and_renders_local_history_items(monkeypatch):
    module = load_module()
    config = {
        "provider": "codex",
        "caution_pct": 60,
        "warn_pct": 80,
        "alert_pct": 100,
        "bar_width": 12,
        "metrics": ["five_hour"],
    }
    provider_result = {
        "status": "ok",
        "reason": "",
        "snapshot_time": "2030-01-01T00:00:00+00:00",
        "source_path": "/tmp/codex.jsonl",
        "cacheable": True,
        "items": [{
            "key": "primary_window",
            "label_en": "5-hour limit",
            "label_jp": "現在のセッション",
            "window_hours": 5,
            "pct": 18,
            "projected": 42,
            "reset": "1時間後にリセット",
            "resets_at_raw": "2030-01-01T01:00:00+00:00",
            "exhaust_info": None,
        }],
    }
    seen = {"provider": None, "saved": [], "notified": [], "rendered": []}
    monkeypatch.setattr(module, "load_config", lambda: config)
    monkeypatch.setattr(module, "load_usage_items", lambda provider, loaded_config: seen.update({
        "provider": provider,
    }) or provider_result)
    monkeypatch.setattr(
        module,
        "save_cache",
        lambda provider, result, cache_source="legacy": seen["saved"].append((provider, result, cache_source)),
    )
    monkeypatch.setattr(module, "check_and_notify", lambda items, loaded_config: seen["notified"].append((items, loaded_config)))
    monkeypatch.setattr(
        module,
        "render_output",
        lambda items, loaded_config, stale_reason=None: seen["rendered"].append((items, loaded_config, stale_reason)),
    )
    monkeypatch.setattr(module, "load_cache", lambda provider: pytest.fail("load_cache should not be called"))

    module.main()

    assert seen["provider"] == "codex"
    assert seen["saved"] == [("codex", provider_result, "local_history")]
    assert seen["notified"] == [(provider_result["items"], config)]
    assert seen["rendered"] == [(provider_result["items"], config, None)]


def test_stale_local_snapshots_render_without_notifications_or_cache_save(monkeypatch):
    module = load_module()
    config = {
        "provider": "codex",
        "caution_pct": 60,
        "warn_pct": 80,
        "alert_pct": 100,
        "bar_width": 12,
        "metrics": ["five_hour"],
    }
    provider_result = {
        "status": "ok",
        "reason": "",
        "snapshot_time": "2026-03-29T00:00:00+00:00",
        "source_path": "/tmp/codex.jsonl",
        "cacheable": True,
        "items": [{
            "key": "primary_window",
            "label_en": "5-hour limit",
            "label_jp": "現在のセッション",
            "window_hours": 5,
            "pct": 18,
            "projected": 42,
            "reset": "まもなくリセット",
            "resets_at_raw": "2026-03-29T01:00:00+00:00",
            "exhaust_info": None,
        }],
    }
    seen = {"saved": [], "notified": 0, "rendered": []}
    fake_now = module.datetime(2026, 3, 30, 0, 0, tzinfo=module.timezone.utc)
    monkeypatch.setattr(module, "load_config", lambda: config)
    monkeypatch.setattr(module, "load_usage_items", lambda provider, loaded_config: provider_result)
    monkeypatch.setattr(
        module,
        "save_cache",
        lambda provider, result, cache_source="legacy": seen["saved"].append((provider, result, cache_source)),
    )
    monkeypatch.setattr(module, "check_and_notify", lambda items, loaded_config: seen.__setitem__("notified", seen["notified"] + 1))
    monkeypatch.setattr(
        module,
        "render_output",
        lambda items, loaded_config, stale_reason=None: seen["rendered"].append((items, loaded_config, stale_reason)),
    )
    monkeypatch.setattr(module, "load_cache", lambda provider: pytest.fail("load_cache should not be called for stale ok results"))

    class FrozenDateTime(module.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fake_now.replace(tzinfo=None)
            return fake_now.astimezone(tz)

    monkeypatch.setattr(module, "datetime", FrozenDateTime)

    module.main()

    assert seen["saved"] == []
    assert seen["notified"] == 0
    assert seen["rendered"] == [(provider_result["items"], config, "ローカル履歴が古いため通知を抑止しています")]


def test_provider_scoped_cache_fallback_renders_stale_cache_for_non_ok_results(monkeypatch):
    module = load_module()
    config = {
        "provider": "codex",
        "caution_pct": 60,
        "warn_pct": 80,
        "alert_pct": 100,
        "bar_width": 12,
        "metrics": ["five_hour"],
    }
    cached_result = {
        "status": "ok",
        "reason": "",
        "snapshot_time": "2030-01-01T00:00:00+00:00",
        "source_path": "/tmp/cache.jsonl",
        "cacheable": True,
        "items": [{
            "key": "primary_window",
            "label_en": "5-hour limit",
            "label_jp": "現在のセッション",
            "window_hours": 5,
            "pct": 23,
            "projected": 40,
            "reset": "2時間後にリセット",
            "resets_at_raw": "2030-01-01T02:00:00+00:00",
            "exhaust_info": None,
        }],
    }
    seen = {"loaded": [], "saved": [], "rendered": [], "local_errors": []}
    monkeypatch.setattr(module, "load_config", lambda: config)
    monkeypatch.setattr(module, "load_usage_items", lambda provider, loaded_config: {
        "status": "unreadable",
        "reason": "history scan failed",
        "snapshot_time": None,
        "source_path": None,
        "cacheable": False,
        "items": [],
    })
    monkeypatch.setattr(module, "load_cache", lambda provider: seen["loaded"].append(provider) or cached_result)
    monkeypatch.setattr(
        module,
        "save_cache",
        lambda provider, result, cache_source="legacy": seen["saved"].append((provider, result, cache_source)),
    )
    monkeypatch.setattr(
        module,
        "render_output",
        lambda items, loaded_config, stale_reason=None: seen["rendered"].append((items, loaded_config, stale_reason)),
    )
    monkeypatch.setattr(module, "render_local_history_error", lambda reason: seen["local_errors"].append(reason))
    monkeypatch.setattr(module, "check_and_notify", lambda items, loaded_config: pytest.fail("check_and_notify should not run on cache fallback"))

    module.main()

    assert seen["loaded"] == ["codex"]
    assert seen["saved"] == []
    assert seen["local_errors"] == []
    assert seen["rendered"] == [(cached_result["items"], config, "history scan failed")]


def test_invalid_provider_behavior_still_renders_config_error_without_loading_provider(monkeypatch):
    module = load_module()
    seen = {"rendered": []}
    monkeypatch.setattr(module, "load_config", lambda: {
        "provider": "nope",
        "caution_pct": 60,
        "warn_pct": 80,
        "alert_pct": 100,
        "bar_width": 12,
        "metrics": [],
    })
    monkeypatch.setattr(module, "load_usage_items", lambda provider, config: pytest.fail("load_usage_items should not be called"))
    monkeypatch.setattr(module, "load_cache", lambda provider: pytest.fail("load_cache should not be called"))
    monkeypatch.setattr(module, "render_config_error", lambda message: seen["rendered"].append(message))

    module.main()

    assert seen["rendered"] == ["unsupported provider: nope"]


def test_wrapper_no_longer_requires_third_party_packages():
    text = Path(SCRIPT).read_text()

    assert "browser_cookie3" not in text
    assert '"requests"' not in text
    assert "<xbar.dependencies>python3</xbar.dependencies>" in text


def test_source_no_longer_references_auth_or_remote_usage_paths():
    text = Path(SCRIPT).read_text()

    assert "auth.json" not in text
    assert "backend-api/wham/usage" not in text
    assert "chatgpt.com/codex/settings/usage" not in text
    assert "api.anthropic.com/api/oauth/usage" not in text
    assert "fetch_usage_browser" not in text
    assert "fetch_usage_oauth" not in text


def test_load_codex_history_items_maps_fields_from_local_snapshot():
    module = load_module()
    fixture = fixture_path("codex-history-primary-secondary.jsonl")

    result = module.load_codex_history_items(session_paths=[fixture], archived_paths=[])

    assert result["status"] == "ok"
    assert result["reason"] == ""
    assert result["snapshot_time"] == "2026-03-29T08:44:18.991000+00:00"
    assert result["source_path"] == str(fixture)
    assert result["cacheable"] is True
    assert [item["key"] for item in result["items"]] == ["primary_window", "secondary_window"]

    primary = result["items"][0]
    assert primary["pct"] == 4
    assert primary["window_hours"] == 5
    assert primary["resets_at_raw"] == "2030-01-01T00:00:00+00:00"
    assert {"label_en", "label_jp", "projected", "reset", "exhaust_info"} <= primary.keys()

    secondary = result["items"][1]
    assert secondary["pct"] == 81
    assert secondary["window_hours"] == 168
    assert secondary["resets_at_raw"] == "2030-01-08T00:00:00+00:00"


def test_load_codex_history_items_uses_globally_newest_snapshot():
    module = load_module()

    result = module.load_codex_history_items(
        session_paths=[
            fixture_path("codex-history-invalid.jsonl"),
            fixture_path("codex-history-primary-secondary.jsonl"),
        ],
        archived_paths=[],
    )

    assert result["status"] == "ok"
    assert result["snapshot_time"] == "2026-03-29T08:44:18.991000+00:00"
    assert result["source_path"].endswith("codex-history-primary-secondary.jsonl")


def test_load_codex_history_items_keeps_windows_from_one_event_when_newest_windows_are_split_across_rows():
    module = load_module()

    result = module.load_codex_history_items(
        session_paths=[fixture_path("codex-history-partial.jsonl")],
        archived_paths=[],
    )

    assert result["status"] == "ok"
    assert result["snapshot_time"] == "2026-03-29T09:10:00+00:00"
    assert [item["key"] for item in result["items"]] == ["primary_window"]
    assert result["items"][0]["pct"] == 7


def test_load_codex_history_items_omits_missing_window_in_partial_snapshot():
    module = load_module()

    result = module.load_codex_history_items(
        session_paths=[fixture_path("codex-history-partial.jsonl")],
        archived_paths=[],
    )

    assert result["status"] == "ok"
    assert result["snapshot_time"] == "2026-03-29T09:10:00+00:00"
    assert [item["key"] for item in result["items"]] == ["primary_window"]
    assert result["items"][0]["pct"] == 7


def test_load_codex_history_items_tolerates_malformed_lines():
    module = load_module()

    result = module.load_codex_history_items(
        session_paths=[fixture_path("codex-history-invalid.jsonl")],
        archived_paths=[],
    )

    assert result["status"] == "ok"
    assert result["snapshot_time"] == "2026-03-29T08:43:00+00:00"
    assert {item["key"]: item["pct"] for item in result["items"]} == {
        "primary_window": 12,
        "secondary_window": 34,
    }


def test_load_codex_history_items_falls_back_to_archived_sessions():
    module = load_module()

    result = module.load_codex_history_items(
        session_paths=[],
        archived_paths=[fixture_path("codex-history-archived-only.jsonl")],
    )

    assert result["status"] == "ok"
    assert result["snapshot_time"] == "2026-03-28T07:00:00+00:00"
    assert result["source_path"].endswith("codex-history-archived-only.jsonl")
    assert [item["key"] for item in result["items"]] == ["primary_window", "secondary_window"]


def test_load_codex_history_items_returns_missing_when_no_files_exist():
    module = load_module()

    result = module.load_codex_history_items(session_paths=[], archived_paths=[])

    assert result["status"] == "missing"
    assert result["items"] == []
    assert result["snapshot_time"] is None
    assert result["source_path"] is None


def test_load_codex_history_items_returns_unreadable_on_io_error(monkeypatch):
    module = load_module()
    monkeypatch.setattr(
        module,
        "iter_jsonl_objects",
        lambda path: (_ for _ in ()).throw(OSError("boom")),
    )

    result = module.load_codex_history_items(
        session_paths=[Path("/tmp/fake.jsonl")],
        archived_paths=[],
    )

    assert result["status"] == "unreadable"
    assert "boom" in result["reason"]


def test_load_codex_history_items_returns_unreadable_when_any_candidate_file_cannot_be_scanned(monkeypatch):
    module = load_module()
    unreadable_path = Path("/tmp/unreadable.jsonl")
    valid_path = fixture_path("codex-history-primary-secondary.jsonl")
    original_iter_jsonl_objects = module.iter_jsonl_objects

    def fake_iter_jsonl_objects(path):
        if Path(path) == unreadable_path:
            raise OSError("boom")
        return original_iter_jsonl_objects(path)

    monkeypatch.setattr(module, "iter_jsonl_objects", fake_iter_jsonl_objects)

    result = module.load_codex_history_items(
        session_paths=[unreadable_path, valid_path],
        archived_paths=[],
    )

    assert result["status"] == "unreadable"
    assert "boom" in result["reason"]


def test_load_codex_history_items_returns_unreadable_when_history_discovery_fails(monkeypatch):
    module = load_module()

    def fake_list_codex_history_paths(root, recursive):
        raise OSError("discovery boom")

    monkeypatch.setattr(module, "list_codex_history_paths", fake_list_codex_history_paths)

    result = module.load_codex_history_items()

    assert result["status"] == "unreadable"
    assert "discovery boom" in result["reason"]


@pytest.mark.parametrize("bad_reset_value", [float("nan"), float("inf"), 10**30])
def test_load_codex_history_items_treats_invalid_numeric_reset_as_missing(tmp_path, bad_reset_value):
    module = load_module()
    fixture = tmp_path / "codex-history-bad-reset.jsonl"
    fixture.write_text(
        json.dumps({
            "type": "event_msg",
            "timestamp": "2026-03-29T10:00:00+00:00",
            "payload": {
                "type": "token_count",
                "rate_limits": {
                    "primary_window": {
                        "used_percent": 17,
                        "window_minutes": 300,
                        "resets_at": bad_reset_value,
                    },
                },
            },
        }) + "\n"
    )

    result = module.load_codex_history_items(session_paths=[fixture], archived_paths=[])

    assert result["status"] == "ok"
    assert [item["key"] for item in result["items"]] == ["primary_window"]
    assert result["items"][0]["pct"] == 17
    assert result["items"][0]["resets_at_raw"] is None
    assert result["items"][0]["reset"] == ""


@pytest.mark.parametrize(
    "overrides",
    [
        {"used_percent": float("nan")},
        {"used_percent": float("inf")},
        {"window_minutes": float("nan")},
        {"window_minutes": None, "limit_window_seconds": float("inf")},
    ],
)
def test_load_codex_history_items_ignores_non_finite_usage_and_window_values(tmp_path, overrides):
    module = load_module()
    fixture = tmp_path / "codex-history-bad-metric.jsonl"
    primary_window = {
        "used_percent": 17,
        "window_minutes": 300,
        "resets_at": "2030-01-01T00:00:00+00:00",
    }
    primary_window.update(overrides)
    fixture.write_text(
        json.dumps({
            "type": "event_msg",
            "timestamp": "2026-03-29T10:00:00+00:00",
            "payload": {
                "type": "token_count",
                "rate_limits": {
                    "primary_window": primary_window,
                },
            },
        }) + "\n"
    )

    result = module.load_codex_history_items(session_paths=[fixture], archived_paths=[])

    assert result["status"] == "unavailable"
    assert result["items"] == []
