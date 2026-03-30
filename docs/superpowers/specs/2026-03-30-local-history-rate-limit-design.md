# Local History Rate Limit Design

**Date:** 2026-03-30

**Goal**

This widget must compute Codex and Claude rate-limit percentages from local history artifacts only. It must stop reading `auth.json`, browser cookies, keychain entries, or any other credential source. If local history does not contain usable quota data, the widget may show cached values or a local-history error, but it must never fall back to credentials or network requests.

## Context

The current script has moved from the original Claude browser-based fetch path toward a Codex-oriented implementation, but it still depends on credentialed sources:

- Codex OAuth via `~/.codex/auth.json` and `https://chatgpt.com/backend-api/wham/usage`
- Browser-cookie parsing of `https://chatgpt.com/codex/settings/usage`

The reference direction from `kentoku24/CodexBar` issue 1 and the surrounding CodexBar history is to prefer local session history, especially `token_count.rate_limits` stored in Codex JSONL session logs, before any status probe or dashboard path.

Local file inspection in this environment showed:

- Codex history exists in `~/.codex/sessions/**/*.jsonl`, `~/.codex/archived_sessions/*.jsonl`, and `~/.codex/session_index.jsonl`
- Codex `event_msg` rows include `payload.type == "token_count"` plus `payload.rate_limits.primary/secondary`
- Claude local history exists in `~/.claude/projects/**/*.jsonl`, `~/.claude/history.jsonl`, and `~/.claude/stats-cache.json`
- Claude files are clearly local-only, but the exact stable quota snapshot shape for percentage-bearing rows still needs characterization during implementation

## Scope

In scope:

- Replace all credentialed fetch paths with local-history readers
- Introduce provider-style local readers for Codex and Claude
- Normalize both providers into the existing `items` shape used by rendering
- Preserve existing menubar/dropdown rendering, burn-rate projection, cache fallback, and notifications where inputs still exist
- Update tests and README for local-history-only behavior

Out of scope:

- Adding any new online fetch path
- Reaching into keychain, cookies, OAuth refresh, or browser sessions as a fallback
- Reworking the overall UI beyond what is required to explain local-history-only failures

## Proposed Architecture

Keep the script as a single executable file for now, but split the data-loading logic into explicit provider helpers:

- `load_usage_items(provider_name, config)`
- `load_codex_history_items()`
- `load_claude_history_items()`
- shared file-scanning and JSONL parsing helpers

Each provider returns a normalized list of items with this shape:

```python
{
    "key": "primary_window",
    "label_en": "5-hour limit",
    "label_jp": "現在のセッション",
    "window_hours": 5,
    "pct": 18,
    "resets_at_raw": "2026-03-30T12:34:56+00:00",
    "projected": None,
    "reset": "",
    "exhaust_info": None,
}
```

The provider layer is responsible only for extracting facts from local files. Existing helpers remain responsible for:

- projected usage calculation
- reset text formatting
- bar rendering
- alert thresholds
- stale cache display

## Provider Design

### Codex History Provider

Codex support is based on confirmed local data shape.

Primary inputs:

- `~/.codex/sessions/**/*.jsonl`
- `~/.codex/archived_sessions/*.jsonl`

Records to inspect:

- JSONL rows where `type == "event_msg"`
- `payload.type == "token_count"`
- `payload.rate_limits` exists

Extraction rules:

- Prefer the newest valid `payload.rate_limits`
- Support both `primary`/`secondary` and the already-known `primary_window`/`secondary_window` naming variants if encountered
- Convert Unix `resets_at` to ISO8601 UTC strings
- Map window minutes or seconds to `window_hours`
- Ignore malformed or partial rows without aborting the scan

Ordering:

- Scan newest files first
- Within a file, the newest valid token-count row wins
- Stop once both primary and secondary windows have been found

Expected output:

- 5-hour session usage
- weekly usage
- optional credits or other windows are ignored unless the current renderer can display them safely

### Claude History Provider

Claude support must remain local-only, but its artifact shape is less certain than Codex in the current workspace scan. The implementation should therefore be structured as a strict local parser with explicit discovery tests.

Primary candidate inputs:

- `~/.claude/projects/**/*.jsonl`
- `~/.claude/history.jsonl`

Optional candidate input:

- `~/.claude/stats-cache.json`

Rules:

- Prefer explicit quota snapshots that contain percentage and reset-time information
- If multiple local file shapes exist, encode them as ordered parsers from most explicit to least explicit
- Do not infer percentages from token counts unless a stable mapping exists in the local artifact itself
- If only textual limit messages exist, treat them as insufficient for `%` output and return no Claude items

Failure policy:

- If Claude local history cannot yield a trustworthy percentage, return no Claude items rather than falling back to credentials
- Surface a local-history-specific message so the limitation is visible and honest

This keeps the contract with the user request: local artifacts only, no secret access, no invented percentages.

## Configuration Changes

Current config still exposes online-oriented `data_source` values such as `oauth` and `browser`. That is misleading once credential access is removed.

Replace or reinterpret configuration as:

- preferred: `provider`: `"codex"` or `"claude"`
- optional compatibility: accept old `data_source` keys but ignore their online meaning

Recommended behavior:

- `provider` selects which local-history parser to run
- old `data_source` values are tolerated for backward compatibility but normalized internally to local history mode
- README examples should move to the new `provider` terminology

If keeping the old config keys is cheaper in the short term, the script should still document that all values now resolve to the same local-history backend.

## Error Handling

Remove all credential and network-specific branches:

- no `requests` exceptions
- no HTTP 401/403 handling
- no token refresh
- no browser-cookie import errors in normal operation

Replace with local-history outcomes:

- local history parsed successfully
- local history missing
- local history unreadable
- local history present but quota fields unavailable

Fallback order:

1. fresh local-history items
2. cached items with stale reason
3. local-history-only error state

The stale reason and empty-state copy should explicitly mention local history, not login state.

## Testing Strategy

Add characterization-style tests around provider parsing and keep rendering tests focused on normalized items.

Required tests:

- Codex parser extracts primary and secondary windows from `token_count.rate_limits`
- Codex parser prefers the latest valid row
- Codex parser falls back from `sessions` to `archived_sessions`
- Codex parser ignores malformed JSONL lines
- Claude parser tests use real redacted fixture rows from the user environment once a stable percentage-bearing shape is identified
- Claude parser returns no items when only insufficient local rows exist
- main flow renders cache fallback when no fresh local data is available
- no test imports or monkeypatches `requests`, browser cookies, or auth-file paths for the new happy path

Fixtures should be checked into the repo as redacted JSONL snippets rather than building complex mocks.

## Implementation Notes

- Prefer filesystem and JSON parsing from the standard library
- Remove `requests` and `browser_cookie3` imports after the migration is complete
- Keep JSONL scanning streaming-friendly so large history files do not need full in-memory loading
- Add small helpers for:
  - expanding candidate roots
  - sorting files by modified time
  - reading files newest-first where practical
  - parsing one JSON object per line safely

## Risks

- Claude local files may not contain reliable percentage snapshots in every environment
- Older Codex session files may use slightly different field names
- Local-history-only behavior may make “first run” empty states more common

Mitigations:

- characterize the exact local file shapes with fixtures before deleting old code
- fail closed for Claude percentages instead of guessing
- preserve cache fallback and make the error copy explicit

## Success Criteria

- The script does not read `auth.json`, cookies, keychain entries, or call remote usage endpoints
- Codex percentage display comes from local session history only
- Claude percentage display also comes from local artifacts only when trustworthy local data exists
- Missing local data results in cache or an honest local-history error, never a credential prompt
- The renderer continues to show percentages and projections for valid local data without behavioral regression
