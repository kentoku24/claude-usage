# Local History Rate Limit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace credential-based Codex and Claude usage fetching with local-history-only parsing, while keeping the existing SwiftBar rendering, cache fallback, and alert workflow intact.

**Architecture:** Keep the current single-file script structure, but formalize a provider layer inside `src/claude-usage.5m.py` that returns structured local-history results. Codex becomes the fully supported local-history provider using JSONL `token_count.rate_limits` snapshots from `~/.codex/sessions` and `~/.codex/archived_sessions`; Claude becomes a strict Phase 1 local provider that only renders percentages when an explicit trustworthy local snapshot exists and otherwise returns an `unavailable` provider result. Legacy `oauth` / `browser` config values are deprecated aliases and no longer enable credential or network fetches.

**Tech Stack:** Python 3.10+ standard library, SwiftBar menu-bar plugin format, `pytest`

---

## File Structure

**Files:**
- Modify: `src/claude-usage.5m.py`
  Responsibility: provider result contract, config migration, local-history scanners, cache metadata, main flow, and rendering integration.
- Modify: `test_claude_usage.py`
  Responsibility: characterization tests for provider parsing, config migration, cache validation, source-level removal assertions, and main-flow behavior.
- Modify: `README.md`
  Responsibility: local-history-only setup and troubleshooting docs.
- Modify: `config.example.json`
  Responsibility: show `provider`-based config and deprecate `data_source`.
- Create: `tests/fixtures/codex-history-primary-secondary.jsonl`
  Responsibility: newest valid Codex `token_count.rate_limits` snapshot with both windows.
- Create: `tests/fixtures/codex-history-partial.jsonl`
  Responsibility: newest valid Codex snapshot with only one usable window.
- Create: `tests/fixtures/codex-history-invalid.jsonl`
  Responsibility: malformed/irrelevant lines used to verify fail-safe parsing.
- Create: `tests/fixtures/codex-history-archived-only.jsonl`
  Responsibility: valid Codex snapshot used when only `archived_sessions` contains local quota data.
- Create: `tests/fixtures/claude-history-unavailable.jsonl`
  Responsibility: readable Claude local history without trustworthy explicit quota percentages, proving Phase 1 fail-closed behavior.

## Data Contracts

Provider result:

```python
{
    "status": "ok",  # ok | missing | unreadable | unavailable
    "reason": "",
    "snapshot_time": "2026-03-30T12:34:56+00:00" or None,
    "source_path": "/Users/.../file.jsonl" or None,
    "cacheable": True,
    "items": [...],
}
```

Cache payload:

```python
{
    "cache_schema_version": 2,
    "cache_source": "local_history",
    "provider": "codex",
    "saved_at": "2026-03-30T12:34:56+00:00",
    "result": {...provider_result...},
}
```

Helper signatures:

```python
def save_cache(provider: str, provider_result: dict) -> None: ...
def load_cache(provider: str) -> dict | None: ...
```

Contract rules:

- `load_cache(provider)` returns `provider_result` only, not the raw cache envelope
- cache reuse is allowed only when `cache_source == "local_history"` and cached `provider` matches the requested provider
- missing windows are omitted from `items`; there is no placeholder item for an unavailable paired window
- invalid `provider` values render a local config error in `main()`; they do not silently fall back

### Task 1: Lock the provider contract, config migration, and cache metadata

**Files:**
- Modify: `src/claude-usage.5m.py`
- Modify: `test_claude_usage.py`

- [ ] **Step 1: Write the failing tests**

Add tests for:

- `load_config()` preferring `provider` over deprecated `data_source`
- deprecated `data_source` values `"oauth"` and `"browser"` normalizing to provider `"codex"`
- invalid `provider` values producing a local config error path
- cache readers rejecting entries without both `cache_source == "local_history"` and matching `provider`
- `main()` rendering a local config error for invalid `provider`

```python
def test_load_config_prefers_provider_over_legacy_data_source(tmp_path, monkeypatch):
    module = load_module()
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"provider": "claude", "data_source": "oauth"}))
    monkeypatch.setattr(module, "CONFIG_PATHS", [config_path])
    config = module.load_config()
    assert config["provider"] == "claude"


def test_load_config_maps_legacy_data_source_to_codex_provider(tmp_path, monkeypatch):
    module = load_module()
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"data_source": "browser"}))
    monkeypatch.setattr(module, "CONFIG_PATHS", [config_path])
    config = module.load_config()
    assert config["provider"] == "codex"


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
    monkeypatch.setattr(module, "CACHE_PATHS", [cache_path])
    assert module.load_cache("codex") is None


def test_main_renders_invalid_provider_config(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "load_config", lambda: {
        "provider": "nope",
        "caution_pct": 60,
        "warn_pct": 80,
        "alert_pct": 100,
        "bar_width": 12,
        "metrics": [],
    })
    monkeypatch.setattr(module, "load_cache", lambda provider: None)
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_claude_usage.py -k "config or cache" -v`
Expected: FAIL because the current script does not have `provider` config, provider-scoped cache metadata, or the new invalid-provider rendering behavior.

- [ ] **Step 3: Write the minimal implementation**

Add:

- `DEFAULT_CONFIG["provider"] = "codex"`
- a config normalizer such as:

```python
def normalize_provider_config(config):
    provider = str(config.get("provider", "")).strip().lower()
    if provider in {"codex", "claude"}:
        config["provider"] = provider
        return config
    legacy = str(config.get("data_source", "")).strip().lower()
    if legacy in {"oauth", "browser"}:
        config["provider"] = "codex"
        return config
    if provider:
        raise RuntimeError(f"unsupported provider: {provider}")
    config["provider"] = "codex"
    return config
```

Define a provider-result contract and cache schema:

```python
{
    "cache_schema_version": 2,
    "cache_source": "local_history",
    "provider": "codex",
    "saved_at": "2026-03-30T12:34:56+00:00",
    "result": {...provider_result...},
}
```

Update cache helpers so they accept `provider` as an argument and only reuse local-history cache entries for the same provider.
Handle invalid provider values by rendering a local config error in `main()`, then attempting no provider load at all.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_claude_usage.py -k "config or cache" -v`
Expected: PASS for config normalization and provider-scoped cache validation tests.

- [ ] **Step 5: Commit**

```bash
git add src/claude-usage.5m.py test_claude_usage.py
git commit -m "feat: add local history provider config and cache metadata"
```

### Task 2: Build Codex local-history parsing with a globally newest snapshot rule

**Files:**
- Create: `tests/fixtures/codex-history-primary-secondary.jsonl`
- Create: `tests/fixtures/codex-history-partial.jsonl`
- Create: `tests/fixtures/codex-history-invalid.jsonl`
- Create: `tests/fixtures/codex-history-archived-only.jsonl`
- Modify: `src/claude-usage.5m.py`
- Modify: `test_claude_usage.py`

- [ ] **Step 1: Write the failing tests**

Add fixture-backed tests for:

- field mapping from local JSON paths to normalized fields
- timestamp precedence for snapshot selection
- same-event snapshot consistency
- partial-window omission behavior
- malformed-line tolerance
- `archived_sessions`-only discovery
- `missing` and `unreadable` status behavior

Use this Codex mapping table as the implementation contract:

- event timestamp: top-level `timestamp`, fallback `payload.timestamp`, fallback file mtime
- primary window object: `payload.rate_limits.primary`, fallback `payload.rate_limits.primary_window`
- secondary window object: `payload.rate_limits.secondary`, fallback `payload.rate_limits.secondary_window`
- percent: `used_percent`, fallback `utilization`, fallback `percentage`, fallback `usage`
- window length: `window_minutes / 60`, fallback `limit_window_seconds / 3600`
- reset time: numeric `resets_at` as Unix seconds, fallback string `resets_at`, fallback `reset_at`

```python
def test_load_codex_history_items_uses_newest_snapshot_from_one_event():
    module = load_module()
    result = module.load_codex_history_items([fixture_path("codex-history-primary-secondary.jsonl")])
    assert result["status"] == "ok"
    assert [item["key"] for item in result["items"]] == ["primary_window", "secondary_window"]
    assert result["snapshot_time"] == "2026-03-29T08:44:18.991000+00:00"
    assert result["items"][0]["pct"] == 4
    assert result["items"][0]["window_hours"] == 5


def test_load_codex_history_items_omits_missing_window_in_partial_snapshot():
    module = load_module()
    result = module.load_codex_history_items([fixture_path("codex-history-partial.jsonl")])
    assert result["status"] == "ok"
    assert [item["key"] for item in result["items"]] == ["primary_window"]


def test_load_codex_history_items_falls_back_to_archived_sessions():
    module = load_module()
    result = module.load_codex_history_items(
        session_paths=[],
        archived_paths=[fixture_path("codex-history-archived-only.jsonl")],
    )
    assert result["status"] == "ok"
    assert result["source_path"].endswith("codex-history-archived-only.jsonl")


def test_load_codex_history_items_returns_missing_when_no_files_exist():
    module = load_module()
    result = module.load_codex_history_items(session_paths=[], archived_paths=[])
    assert result["status"] == "missing"


def test_load_codex_history_items_returns_unreadable_on_io_error(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "iter_jsonl_objects", lambda path: (_ for _ in ()).throw(OSError("boom")))
    result = module.load_codex_history_items(session_paths=[Path("/tmp/fake.jsonl")], archived_paths=[])
    assert result["status"] == "unreadable"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_claude_usage.py -k "codex_history" -v`
Expected: FAIL because the current script only knows credential/network Codex loaders and has no Codex JSONL parser.

- [ ] **Step 3: Write the minimal implementation**

Add streaming JSONL helpers:

```python
def iter_jsonl_objects(path):
    with path.open() as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except Exception:
                continue
```

Add Codex scanner helpers that:

- expand roots for `~/.codex/sessions/**/*.jsonl` and `~/.codex/archived_sessions/*.jsonl`
- extract candidate snapshots from `event_msg` + `payload.type == "token_count"`
- normalize all windows from the same event
- choose the globally newest candidate by parsed event timestamp
- return `missing` when no candidate files exist
- return `unreadable` when filesystem or JSONL iteration errors prevent a trustworthy scan
- return:

```python
{
    "status": "ok",
    "reason": "",
    "snapshot_time": "...",
    "source_path": "...jsonl",
    "cacheable": True,
    "items": [...],  # omit missing windows entirely
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_claude_usage.py -k "codex_history" -v`
Expected: PASS for Codex fixture parsing, newest-snapshot selection, partial-window omission, archived fallback, and status outcomes.

- [ ] **Step 5: Commit**

```bash
git add src/claude-usage.5m.py test_claude_usage.py tests/fixtures/codex-history-primary-secondary.jsonl tests/fixtures/codex-history-partial.jsonl tests/fixtures/codex-history-invalid.jsonl
git commit -m "feat: parse codex rate limits from local history"
```

### Task 3: Wire provider dispatch, freshness, cache fallback, and local-history error rendering

**Files:**
- Modify: `src/claude-usage.5m.py`
- Modify: `test_claude_usage.py`

- [ ] **Step 1: Write the failing tests**

Add tests that:

- `main()` loads the provider selected by config
- stale local snapshots suppress notifications
- local-history cache fallback works only for the active provider

```python
def test_main_uses_codex_provider_and_renders_local_history(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "load_config", lambda: {
        "provider": "codex",
        "caution_pct": 60,
        "warn_pct": 80,
        "alert_pct": 100,
        "bar_width": 12,
        "metrics": [],
    })
    monkeypatch.setattr(module, "load_usage_items", lambda provider, config: {
        "status": "ok",
        "reason": "",
        "snapshot_time": "2026-03-30T12:00:00+00:00",
        "source_path": "/tmp/codex.jsonl",
        "cacheable": True,
        "items": [{"key": "primary_window", "label_en": "5-hour limit", "label_jp": "現在のセッション", "window_hours": 5, "pct": 18, "resets_at_raw": "2099-03-30T12:00:00+00:00", "projected": None, "reset": "", "exhaust_info": None}],
    })
    ...


def test_main_uses_provider_scoped_cache_for_missing_local_history(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "load_config", lambda: {
        "provider": "codex",
        "caution_pct": 60,
        "warn_pct": 80,
        "alert_pct": 100,
        "bar_width": 12,
        "metrics": [],
    })
    monkeypatch.setattr(module, "load_usage_items", lambda provider, config: {
        "status": "missing",
        "reason": "No Codex history files found.",
        "snapshot_time": None,
        "source_path": None,
        "cacheable": False,
        "items": [],
    })
    monkeypatch.setattr(module, "load_cache", lambda provider: {
        "status": "ok",
        "reason": "",
        "snapshot_time": "2026-03-30T12:00:00+00:00",
        "source_path": "/tmp/cached.jsonl",
        "cacheable": True,
        "items": [{"key": "primary_window", "label_en": "5-hour limit", "label_jp": "現在のセッション", "window_hours": 5, "pct": 18, "resets_at_raw": "2000-03-30T12:00:00+00:00", "projected": None, "reset": "", "exhaust_info": None}],
    })
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_claude_usage.py -k "main_uses_codex_provider or provider_scoped_cache or invalid_provider" -v`
Expected: FAIL because `main()` still dispatches `oauth` / `browser` code and does not yet have the new provider-result flow.

- [ ] **Step 3: Write the minimal implementation**

Replace `fetch_usage_oauth()` / `fetch_usage_browser()` dispatch with:

```python
def load_usage_items(provider, config):
    if provider == "codex":
        return load_codex_history_items()
    if provider == "claude":
        return load_claude_history_items()
    raise RuntimeError(f"unsupported provider: {provider}")
```

Update `main()` to consume provider results:

- `status == "ok"` with future reset timestamps: render and cache
- `status == "ok"` but stale: render stale without notifications
- other statuses: try provider-scoped local-history cache, otherwise show local-history-only error

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_claude_usage.py -k "main_uses_codex_provider or provider_scoped_cache or invalid_provider or cache" -v`
Expected: PASS for provider dispatch, freshness, provider-scoped cache fallback, and local-history error rendering.

- [ ] **Step 5: Commit**

```bash
git add src/claude-usage.5m.py test_claude_usage.py
git commit -m "refactor: switch usage loading to local history providers"
```

### Task 4: Remove remote fetch code from the wrapper, metadata, and runtime

**Files:**
- Modify: `src/claude-usage.5m.py`
- Modify: `test_claude_usage.py`

- [ ] **Step 1: Write the failing tests**

Add source/runtime tests that assert:

- the polyglot shell wrapper no longer checks for `requests` or `browser_cookie3`
- SwiftBar dependency metadata no longer advertises third-party packages
- the module imports with only standard-library dependencies
- runtime source text no longer references credential/network fetch constants and helpers

```python
def test_wrapper_no_longer_requires_third_party_packages():
    text = SCRIPT.read_text()
    assert "browser_cookie3" not in text
    assert '"requests"' not in text
    assert "<xbar.dependencies>python3</xbar.dependencies>" in text


def test_source_no_longer_references_auth_or_remote_usage_paths():
    text = SCRIPT.read_text()
    assert "auth.json" not in text
    assert "backend-api/wham/usage" not in text
    assert "chatgpt.com/codex/settings/usage" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_claude_usage.py -k "wrapper_no_longer or source_no_longer_references_auth" -v`
Expected: FAIL because the current executable header and metadata still mention remote dependencies and runtime source still contains remote-fetch strings.

- [ ] **Step 3: Write the minimal implementation**

Delete or replace:

- bash bootstrap checks for `requests` / `browser_cookie3`
- `<xbar.dependencies>` references to third-party packages
- all runtime imports and helpers for cookies, auth, HTTP, remote URLs, and token refresh

Keep only standard-library imports plus local filesystem parsing.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_claude_usage.py -k "wrapper_no_longer or source_no_longer_references_auth" -v`
Expected: PASS, proving wrapper, metadata, and runtime code no longer depend on remote-fetch infrastructure.

- [ ] **Step 5: Commit**

```bash
git add src/claude-usage.5m.py test_claude_usage.py
git commit -m "refactor: remove remote fetch dependencies"
```

### Task 5: Add Claude Phase 1 local provider with fail-closed behavior

**Files:**
- Create: `tests/fixtures/claude-history-unavailable.jsonl`
- Modify: `src/claude-usage.5m.py`
- Modify: `test_claude_usage.py`

- [ ] **Step 1: Write the failing tests**

Add tests for:

- `load_claude_history_items()` returning `status == "unavailable"` when readable local files do not contain an explicit percentage plus an unambiguous reset field that can be normalized to an absolute timestamp
- `load_claude_history_items()` returning `missing` when no candidate files exist
- `load_claude_history_items()` returning `unreadable` when candidate files cannot be read
- `main()` rendering a local-history-only Claude error when provider is `claude` and no provider-scoped cache exists

Concrete Phase 1 contract:

- this plan intentionally uses a stricter rule than the spec wording: accept only rows whose reset field can be normalized to an absolute timestamp at parse time, because freshness and cache eligibility depend on absolute time
- do not parse free-form transcript summaries
- do not use `~/.claude/stats-cache.json` for `%`

```python
def test_load_claude_history_items_returns_unavailable_for_non_quota_history():
    module = load_module()
    result = module.load_claude_history_items([fixture_path("claude-history-unavailable.jsonl")])
    assert result["status"] == "unavailable"
    assert result["items"] == []


def test_load_claude_history_items_returns_missing_when_no_files_exist():
    module = load_module()
    result = module.load_claude_history_items([])
    assert result["status"] == "missing"


def test_load_claude_history_items_returns_unreadable_on_io_error(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "iter_jsonl_objects", lambda path: (_ for _ in ()).throw(OSError("boom")))
    result = module.load_claude_history_items([Path("/tmp/fake.jsonl")])
    assert result["status"] == "unreadable"


def test_main_renders_claude_local_history_unavailable(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "load_config", lambda: {
        "provider": "claude",
        "caution_pct": 60,
        "warn_pct": 80,
        "alert_pct": 100,
        "bar_width": 12,
        "metrics": [],
    })
    monkeypatch.setattr(module, "load_usage_items", lambda provider, config: {
        "status": "unavailable",
        "reason": "Claude local history does not contain explicit quota snapshots.",
        "snapshot_time": None,
        "source_path": None,
        "cacheable": False,
        "items": [],
    })
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_claude_usage.py -k "claude_history_items or claude_local_history_unavailable" -v`
Expected: FAIL because no Claude local-history provider exists yet.

- [ ] **Step 3: Write the minimal implementation**

Implement `load_claude_history_items()` to:

- scan `~/.claude/projects/**/*.jsonl` and `~/.claude/history.jsonl`
- look only for explicit machine-readable percentage + reset fields that normalize to absolute timestamps
- return `missing` when no candidate files exist
- return `unreadable` when filesystem or JSONL iteration errors prevent a trustworthy scan
- return `unavailable` with no items when none are found

Keep the implementation intentionally conservative:

```python
return {
    "status": "unavailable",
    "reason": "Claude local history does not contain explicit quota snapshots.",
    "snapshot_time": None,
    "source_path": None,
    "cacheable": False,
    "items": [],
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_claude_usage.py -k "claude_history_items or claude_local_history_unavailable" -v`
Expected: PASS for Phase 1 fail-closed Claude behavior.

- [ ] **Step 5: Commit**

```bash
git add src/claude-usage.5m.py test_claude_usage.py tests/fixtures/claude-history-unavailable.jsonl
git commit -m "feat: add phase 1 claude local history provider"
```

### Task 6: Update docs and run final verification

**Files:**
- Modify: `README.md`
- Modify: `config.example.json`
- Modify: `src/claude-usage.5m.py`
- Modify: `test_claude_usage.py`

- [ ] **Step 1: Write the failing docs/behavior tests**

Add tests that verify:

- `config.example.json` uses `provider`
- README no longer tells users to log in, install `requests`, or rely on cookies/auth files for quota fetching
- the wrapper metadata no longer advertises third-party dependencies
- user-facing error output mentions local history rather than authentication

```python
def test_readme_documents_local_history_only():
    text = Path("README.md").read_text()
    assert '"provider"' in text
    assert "auth.json" not in text
    assert "browser-cookie3" not in text


def test_config_example_uses_provider_field():
    config = json.loads(Path("config.example.json").read_text())
    assert config["provider"] == "codex"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_claude_usage.py -k "readme_documents_local_history_only or config_example_uses_provider_field" -v`
Expected: FAIL because docs and config still describe remote/credentialed fetching.

- [ ] **Step 3: Write the minimal implementation**

Update docs to say:

- quota percentages come from local history only
- `provider` selects `codex` or `claude`
- deprecated `data_source` values are accepted only for compatibility
- first-run empty states are normal when no local history exists yet

Update `config.example.json` to:

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

- [ ] **Step 4: Run the full verification suite**

Run: `python3 -m pytest test_claude_usage.py -v`
Expected: all tests PASS.

Run: `bash src/claude-usage.5m.py`
Expected: SwiftBar-formatted output that either shows local-history percentages or a local-history-specific fallback message, with no import/network/auth errors.

- [ ] **Step 5: Commit**

```bash
git add README.md config.example.json src/claude-usage.5m.py test_claude_usage.py tests/fixtures
git commit -m "docs: document local history rate limit mode"
```
