"""
Codex usage widget の最小テスト:
1. Codex API payload から usage アイテムを抽出できる
2. Codex auth.json を読んで backend-api/wham/usage を呼べる
"""

import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "src" / "claude-usage.5m.py"


def load_module():
    spec = importlib.util.spec_from_file_location("codex_usage", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sample_payload():
    return {
        "rate_limit": {
            "primary_window": {
                "used_percent": 18,
                "limit_window_seconds": 18000,
                "reset_after_seconds": 9000,
                "reset_at": 1774466160,
            },
            "secondary_window": {
                "used_percent": 41,
                "limit_window_seconds": 604800,
                "reset_after_seconds": 255832,
                "reset_at": 1774711988,
            },
        }
    }


def test_extract_usage_items_from_codex_payload():
    module = load_module()
    items = module.extract_usage_items_from_codex_payload(sample_payload())
    assert [item["key"] for item in items] == ["primary_window", "secondary_window"]
    assert items[0]["pct"] == 18
    assert items[1]["window_hours"] == 168
    assert items[0]["resets_at_raw"].endswith("+00:00")


def test_fetch_usage_oauth_uses_auth_json_and_api(tmp_path, monkeypatch):
    module = load_module()
    auth_path = tmp_path / "auth.json"
    auth_path.write_text(json.dumps({
        "tokens": {
            "access_token": "access-123",
            "refresh_token": "refresh-456",
        },
        "last_refresh": "2026-03-26T00:00:00Z",
    }))

    monkeypatch.setattr(module, "CODEX_AUTH_PATHS", [auth_path])
    monkeypatch.setattr(module, "codex_needs_refresh", lambda auth: False)

    captured = {}

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse(sample_payload())

    monkeypatch.setattr(module.requests, "get", fake_get)

    items = module.fetch_usage_oauth()
    assert captured["url"] == module.CODEX_API_URL
    assert captured["headers"]["Authorization"] == "Bearer access-123"
    assert [item["key"] for item in items] == ["primary_window", "secondary_window"]


def test_main_renders_codex_usage_url(monkeypatch):
    module = load_module()
    items = module.extract_usage_items_from_codex_payload(sample_payload())

    monkeypatch.setattr(module, "load_config", lambda: {
        "caution_pct": 60,
        "warn_pct": 80,
        "alert_pct": 100,
        "bar_width": 12,
        "metrics": [],
        "data_source": "oauth",
    })
    monkeypatch.setattr(module, "fetch_usage_oauth", lambda: items)
    monkeypatch.setattr(module, "check_and_notify", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "save_cache", lambda *args, **kwargs: None)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        module.main()

    output = buffer.getvalue()
    first_line = output.splitlines()[0]
    assert "%" in first_line
    assert module.USAGE_URL in output
    assert "→" in output
