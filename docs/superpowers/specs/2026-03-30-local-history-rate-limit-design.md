# Local History Rate Limit Design

**Date:** 2026-03-30

**Goal**

This widget must compute Codex and Claude rate-limit percentages from local history artifacts only when trustworthy local quota snapshots exist. It must stop reading `auth.json`, browser cookies, keychain entries, or any other credential source. If local history does not contain usable quota data, the widget may show a cache that was itself derived from local history, or a local-history error, but it must never fall back to credentials or network requests.

## Context

The current script has moved from the original Claude browser-based fetch path toward a Codex-oriented implementation, but it still depends on credentialed sources:

- Codex OAuth via `~/.codex/auth.json` and `https://chatgpt.com/backend-api/wham/usage`
- Browser-cookie parsing of `https://chatgpt.com/codex/settings/usage`

The reference direction from `kentoku24/CodexBar` issue 1 and the surrounding CodexBar history is to prefer local session history, especially `token_count.rate_limits` stored in Codex JSONL session logs, before any status probe or dashboard path.

Local file inspection in this environment showed:

- Codex history exists in `~/.codex/sessions/**/*.jsonl`, `~/.codex/archived_sessions/*.jsonl`, and `~/.codex/session_index.jsonl`
- Codex `event_msg` rows include `payload.type == "token_count"` plus `payload.rate_limits.primary/secondary`
- Claude local history exists in `~/.claude/projects/**/*.jsonl`, `~/.claude/history.jsonl`, and `~/.claude/stats-cache.json`
- Claude files are clearly local-only, but the inspected files did not yet reveal a stable percentage-bearing quota snapshot

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
- The selected Codex snapshot must come from one `token_count.rate_limits` event
- Do not merge primary from one event with secondary from another event
- If the newest valid snapshot contains only one usable window, render only that window and mark the rest unavailable

Expected output:

- 5-hour session usage
- weekly usage
- optional credits or other windows are ignored unless the current renderer can display them safely

### Claude History Provider

Claude support must also remain local-only, but unlike Codex we do not yet have a confirmed percentage-bearing quota snapshot from the inspected files. To keep the design implementable without hidden private-session assumptions, Claude is split into two explicit phases.

Phase 1 contract:

- Inputs are limited to `~/.claude/projects/**/*.jsonl` and `~/.claude/history.jsonl`
- The parser only accepts explicit local rows that already contain both:
  - a percentage value
  - a reset timestamp or reset description that can be normalized
- The parser may use regex extraction from saved assistant text if the `%` and reset details are present in the transcript itself
- The parser must not derive percentages from token counts, message counts, or `~/.claude/stats-cache.json`
- If no explicit percentage-bearing local row exists, Claude returns no items

Phase 1 user-visible behavior:

- Claude credential and network access is removed immediately
- Claude shows a local-history-unavailable state until an explicit local quota snapshot is found
- No guessed or synthesized `%` values are allowed

Phase 2 gate:

- Once one stable local Claude artifact shape is identified, add a redacted fixture to the repo
- Promote that shape into a first-class parser with dedicated tests
- Only after that fixture exists may Claude percentage display be considered fully supported

This keeps the contract with the user request: local artifacts only, no secret access, no invented percentages, and no hidden dependency on manual local-history discovery during implementation.

## Configuration Changes

Current config still exposes online-oriented `data_source` values such as `oauth` and `browser`. That is misleading once credential access is removed.

Replace or reinterpret configuration as:

- preferred: `provider`: `"codex"` or `"claude"`
- optional compatibility: accept old `data_source` keys but ignore their online meaning

Recommended behavior:

- `provider` selects which local-history parser to run
- old `data_source` values are accepted only as deprecated aliases
- every legacy `data_source` value normalizes internally to the same local-history mode
- README examples should move to the new `provider` terminology

Exact migration rule:

- no warning banner is required in the widget UI
- README and config examples must mark `data_source` as deprecated
- tests must verify that `"oauth"` and `"browser"` no longer change runtime behavior

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
2. local-history cache items with stale reason
3. local-history-only error state

The stale reason and empty-state copy should explicitly mention local history, not login state.

Freshness rule:

- a parsed local snapshot is fresh if at least one returned window has `resets_at` in the future
- a parsed local snapshot becomes stale once all returned windows have reset timestamps in the past or missing reset metadata
- projections and notifications run only for fresh local snapshots

Cache migration rule:

- cached payloads must be versioned with metadata such as `cache_schema_version` and `cache_source`
- only caches stamped with `cache_source == "local_history"` are eligible after rollout
- old caches created by browser, OAuth, or unknown sources must be ignored

## Testing Strategy

Add characterization-style tests around provider parsing and keep rendering tests focused on normalized items.

Required tests:

- Codex parser extracts primary and secondary windows from `token_count.rate_limits`
- Codex parser prefers the latest valid row
- Codex parser keeps all rendered windows from the same snapshot event
- Codex parser renders partial data when only one window exists in the newest valid snapshot
- Codex parser falls back from `sessions` to `archived_sessions`
- Codex parser ignores malformed JSONL lines
- Claude parser tests use committed redacted fixture rows only after a stable explicit percentage-bearing local transcript shape is identified
- Claude parser returns no items when only insufficient local rows exist
- Legacy cache entries without `cache_source == "local_history"` are ignored
- Legacy `data_source` values do not change runtime behavior
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

- characterize the exact local Claude file shape behind a committed fixture before claiming full Claude percentage support
- fail closed for Claude percentages instead of guessing
- preserve cache fallback and make the error copy explicit

## Success Criteria

- The script does not read `auth.json`, cookies, keychain entries, or call remote usage endpoints
- Codex percentage display comes from local session history only
- Claude percentage display also comes from local artifacts only when trustworthy local data exists
- Missing local data results in cache or an honest local-history error, never a credential prompt
- The renderer continues to show percentages and projections for valid local data without behavioral regression
