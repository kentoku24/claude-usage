# Codex Usage Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the SwiftBar widget so it can show Codex usage from `https://chatgpt.com/codex/settings/usage` with the same menu-bar workflow and alert behavior.

**Architecture:** Keep the current single-file script structure, but introduce a small provider layer so product-specific values such as base URLs, help links, labels, and fetch logic are centralized. For Codex, fetch the usage page with logged-in ChatGPT session cookies and extract usage data from embedded JSON or other structured page data, so the parsing logic is isolated if the page shape changes.

**Tech Stack:** Python 3.10+, `requests`, `browser_cookie3`, SwiftBar menu-bar plugin format, `pytest`

---

### Task 1: Add Codex provider scaffolding

**Files:**
- Modify: `src/claude-usage.5m.py`
- Test: `test_claude_usage.py`

- [ ] **Step 1: Write the failing test**

Add a unit test that imports a new provider helper and asserts the Codex provider exposes the expected product name and usage page URL.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_claude_usage.py -v`
Expected: fail because the Codex provider helper does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add constants/helpers for product branding, `https://chatgpt.com/codex/settings/usage`, and any product-specific labels used in menu text.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_claude_usage.py -v`
Expected: pass for the new provider helper test.

- [ ] **Step 5: Commit**

```bash
git add src/claude-usage.5m.py test_claude_usage.py
git commit -m "feat: add codex provider scaffolding"
```

### Task 2: Implement Codex usage fetching

**Files:**
- Modify: `src/claude-usage.5m.py`
- Test: `test_claude_usage.py`

- [ ] **Step 1: Write the failing test**

Add tests for a new Codex HTML parser helper using a small fixture string that contains embedded JSON with `utilization` and `resets_at` fields.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_claude_usage.py -v`
Expected: fail because the parser helper is not implemented yet.

- [ ] **Step 3: Write minimal implementation**

Implement a `fetch_usage_codex()` path that requests the usage page, extracts structured JSON from the HTML when possible, and normalizes it into the same `items` shape used by the renderer.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_claude_usage.py -v`
Expected: pass for the parser tests.

- [ ] **Step 5: Commit**

```bash
git add src/claude-usage.5m.py test_claude_usage.py
git commit -m "feat: fetch codex usage data"
```

### Task 3: Rebrand menu output and docs

**Files:**
- Modify: `src/claude-usage.5m.py`
- Modify: `README.md`
- Test: `test_claude_usage.py`

- [ ] **Step 1: Write the failing test**

Add a formatting test that verifies the fallback/error strings and footer link use the Codex usage URL instead of the Claude URL.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_claude_usage.py -v`
Expected: fail until all user-visible strings are updated.

- [ ] **Step 3: Write minimal implementation**

Update title text, error messages, footer links, and README instructions so the widget reads as a Codex usage widget instead of Claude usage.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_claude_usage.py -v`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/claude-usage.5m.py README.md test_claude_usage.py
git commit -m "docs: rebrand widget for codex usage"
```

### Task 4: Verification

**Files:**
- Modify: `src/claude-usage.5m.py`
- Modify: `test_claude_usage.py`

- [ ] **Step 1: Run the full test suite**

Run: `python3 -m pytest -v`
Expected: all tests pass.

- [ ] **Step 2: Smoke-check the script output**

Run: `bash src/claude-usage.5m.py`
Expected: a SwiftBar-formatted menu-bar title and dropdown output without syntax errors.

- [ ] **Step 3: Commit**

```bash
git add src/claude-usage.5m.py test_claude_usage.py README.md
git commit -m "test: verify codex usage widget"
```
