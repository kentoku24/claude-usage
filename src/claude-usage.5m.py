#!/bin/bash
# -*- coding: utf-8 -*-
''''true
# bash/python polyglot: Python 3.10+ を自動検出
# 1st pass: browser_cookie3 あり（browser モード用）
for py in $("$SHELL" -lic 'which -a python3' 2>/dev/null); do
    "$py" -c 'import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)' 2>/dev/null || continue
    "$py" -c 'import browser_cookie3' 2>/dev/null || continue
    exec "$py" "$0"
done
# 2nd pass: requests のみ（oauth モード用）
for py in $("$SHELL" -lic 'which -a python3' 2>/dev/null); do
    "$py" -c 'import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)' 2>/dev/null || continue
    "$py" -c 'import requests' 2>/dev/null || continue
    exec "$py" "$0"
done
echo "⚠️ Claude | color=gray"
echo "---"
echo "pip3 install requests (Python 3.10+)"
exit
'''
#
# <xbar.title>Claude Usage</xbar.title>
# <xbar.version>v2.1</xbar.version>
# <xbar.author>kmatsunami</xbar.author>
# <xbar.desc>Claude.ai の使用量（セッション / 全モデル / Sonnet）をメニューバーに表示</xbar.desc>
# <xbar.dependencies>python3,browser-cookie3,requests</xbar.dependencies>
#
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>false</swiftbar.hideRunInTerminal>
# <swiftbar.hideLastUpdated>false</swiftbar.hideLastUpdated>
# <swiftbar.hideDisablePlugin>false</swiftbar.hideDisablePlugin>
# <swiftbar.hideSwiftBar>false</swiftbar.hideSwiftBar>
#
# セットアップ:
#   pip3 install browser-cookie3 requests
#   このファイルを SwiftBar のプラグインフォルダにコピーして chmod +x
#
# カスタマイズ:
#   ~/.claude-usage-config.json を作成して設定を上書き可能
#   例: {"warn_pct": 70, "alert_pct": 90, "bar_width": 16,
#        "metrics": ["five_hour", "seven_day"]}

import sys
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("⚠️ Claude Usage")
    print("---")
    print("依存ライブラリ不足: requests")
    print("ターミナルで実行してください | size=11 color=gray")
    print("pip3 install requests | bash=/bin/sh "
          "param1=-c param2='pip3 install requests' terminal=true")
    sys.exit(0)

try:
    import browser_cookie3
    HAS_BROWSER_COOKIE3 = True
except ImportError:
    HAS_BROWSER_COOKIE3 = False

BASE_URL        = "https://claude.ai"
OAUTH_API_URL   = "https://api.anthropic.com/api/oauth/usage"
CONFIG_PATH     = Path.home() / ".claude-usage-config.json"
CONFIG_PATHS    = [CONFIG_PATH]
ALERT_STATE_PATH = Path.home() / ".claude-usage-alerted.json"
CACHE_PATH      = Path.home() / ".claude-usage-cache.json"
CACHE_PATHS     = [CACHE_PATH]
CODEX_SESSIONS_ROOT = Path.home() / ".codex" / "sessions"
CODEX_ARCHIVED_SESSIONS_ROOT = Path.home() / ".codex" / "archived_sessions"

# デフォルト設定（~/.claude-usage-config.json で上書き可能）
DEFAULT_CONFIG = {
    "caution_pct": 60,  # 予測使用率の注意閾値（🟡）
    "warn_pct":    80,  # 予測使用率の警告閾値（🟠）
    "alert_pct":  100,  # 予測使用率のアラート閾値（🔴）
    "bar_width": 12,    # プログレスバーの幅（文字数）
    "metrics": ["five_hour", "seven_day", "seven_day_sonnet"],  # 表示する指標
    "provider": "codex",
    # データ取得方式: "browser"（browser_cookie3 + claude.ai API）
    #               "oauth" （macOS Keychain の OAuth トークン + api.anthropic.com）
    "data_source": "oauth",
}

# 全指標の定義  (key, label_en, label_jp, window_hours)
ALL_METRICS = [
    ("five_hour",        "Session", "現在のセッション",   5),
    ("seven_day",        "All",     "すべてのモデル",    168),
    ("seven_day_sonnet", "Sonnet",  "Sonnet のみ",      168),
]

# ── 設定ロード ───────────────────────────────────────────────
def normalize_provider_config(config):
    provider = str(config.get("provider", "")).strip().lower()
    if provider in {"codex", "claude"}:
        config["provider"] = provider
        return config
    if provider:
        raise RuntimeError(f"unsupported provider: {provider}")

    legacy = str(config.get("data_source", "")).strip().lower()
    if legacy in {"oauth", "browser"}:
        config["provider"] = "codex"
        return config

    config["provider"] = "codex"
    return config


def load_config():
    config = dict(DEFAULT_CONFIG)
    for config_path in CONFIG_PATHS:
        if not config_path.exists():
            continue
        try:
            user = json.loads(config_path.read_text())
            for k, v in user.items():
                if k in DEFAULT_CONFIG:
                    config[k] = v
            break
        except Exception:
            break
    return normalize_provider_config(config)

# ── 通知アラート ─────────────────────────────────────────────
def load_alert_state():
    """送信済みアラートの状態を読み込む。"""
    if ALERT_STATE_PATH.exists():
        try:
            return json.loads(ALERT_STATE_PATH.read_text())
        except Exception:
            pass
    return {}

def save_alert_state(state):
    try:
        ALERT_STATE_PATH.write_text(json.dumps(state, indent=2))
    except Exception:
        pass

# ── 前回値キャッシュ ──────────────────────────────────────────
def save_cache(provider, provider_result, cache_source="legacy"):
    """正常取得時の provider_result をキャッシュに保存する。"""
    try:
        CACHE_PATHS[0].write_text(json.dumps({
            "cache_schema_version": 2,
            "cache_source": cache_source,
            "provider": provider,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "result": provider_result,
        }, ensure_ascii=False, indent=2))
    except Exception:
        pass

def load_cache(provider):
    """前回の provider_result をキャッシュから読み込む。なければ None。"""
    for cache_path in CACHE_PATHS:
        if not cache_path.exists():
            continue
        try:
            payload = json.loads(cache_path.read_text())
            if payload.get("cache_source") != "local_history":
                continue
            if payload.get("provider") != provider:
                continue
            result = payload.get("result")
            if isinstance(result, dict) and isinstance(result.get("items"), list):
                return result
        except Exception:
            continue
    return None


def make_provider_result(status, reason="", snapshot_time=None, source_path=None, cacheable=False, items=None):
    return {
        "status": status,
        "reason": reason,
        "snapshot_time": snapshot_time,
        "source_path": source_path,
        "cacheable": cacheable,
        "items": items or [],
    }


def iter_jsonl_objects(path):
    with Path(path).open(encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except Exception:
                continue


def list_codex_history_paths(root, recursive):
    root = Path(root)
    if not root.exists():
        return []
    if recursive:
        return sorted(root.rglob("*.jsonl"))
    return sorted(root.glob("*.jsonl"))


def parse_iso_datetime(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def coerce_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def first_number(*values):
    for value in values:
        number = coerce_number(value)
        if number is not None:
            return number
    return None


def normalize_window_hours(window):
    minutes = coerce_number(window.get("window_minutes"))
    if minutes is not None:
        hours = minutes / 60
        return int(hours) if float(hours).is_integer() else hours

    seconds = coerce_number(window.get("limit_window_seconds"))
    if seconds is not None:
        hours = seconds / 3600
        return int(hours) if float(hours).is_integer() else hours

    return None


def normalize_reset_time(window):
    resets_at = window.get("resets_at")
    if isinstance(resets_at, (int, float)) and not isinstance(resets_at, bool):
        try:
            return datetime.fromtimestamp(resets_at, timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    parsed_resets_at = parse_iso_datetime(resets_at)
    if parsed_resets_at is not None:
        return parsed_resets_at.isoformat()

    reset_at = window.get("reset_at")
    if isinstance(reset_at, (int, float)) and not isinstance(reset_at, bool):
        try:
            return datetime.fromtimestamp(reset_at, timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    parsed_reset_at = parse_iso_datetime(reset_at)
    if parsed_reset_at is not None:
        return parsed_reset_at.isoformat()

    return None


def get_codex_window(rate_limits, key):
    if key == "primary_window":
        return rate_limits.get("primary") or rate_limits.get("primary_window")
    if key == "secondary_window":
        return rate_limits.get("secondary") or rate_limits.get("secondary_window")
    return None


def codex_window_labels(key, window_hours):
    if key == "primary_window":
        return "5-hour limit", "現在のセッション"
    if key == "secondary_window":
        if window_hours == 168:
            return "7-day limit", "7日間の上限"
        return "secondary limit", "補助ウィンドウ"
    return "usage limit", "使用量"


def normalize_codex_window(key, raw_window):
    if not isinstance(raw_window, dict):
        return None

    pct = first_number(
        raw_window.get("used_percent"),
        raw_window.get("utilization"),
        raw_window.get("percentage"),
        raw_window.get("usage"),
    )
    window_hours = normalize_window_hours(raw_window)
    if pct is None or window_hours is None:
        return None

    pct = int(pct) if float(pct).is_integer() else pct
    resets_at_raw = normalize_reset_time(raw_window)
    label_en, label_jp = codex_window_labels(key, window_hours)
    projected = calc_projected(pct, resets_at_raw, window_hours)

    return {
        "key": key,
        "label_en": label_en,
        "label_jp": label_jp,
        "window_hours": window_hours,
        "pct": pct,
        "resets_at_raw": resets_at_raw,
        "projected": projected,
        "reset": format_reset(resets_at_raw),
        "exhaust_info": calc_exhaust_info(pct, projected, resets_at_raw, window_hours),
    }


def extract_codex_snapshot_time(record, payload, path):
    for candidate in (record.get("timestamp"), payload.get("timestamp")):
        parsed = parse_iso_datetime(candidate)
        if parsed is not None:
            return parsed
    return datetime.fromtimestamp(Path(path).stat().st_mtime, timezone.utc)


def extract_codex_snapshot(path, record):
    if not isinstance(record, dict):
        return None
    if record.get("type") != "event_msg":
        return None

    payload = record.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "token_count":
        return None

    rate_limits = payload.get("rate_limits")
    if not isinstance(rate_limits, dict):
        return None

    items = []
    for key in ("primary_window", "secondary_window"):
        item = normalize_codex_window(key, get_codex_window(rate_limits, key))
        if item is not None:
            items.append(item)

    if not items:
        return None

    snapshot_dt = extract_codex_snapshot_time(record, payload, path)
    return {
        "snapshot_dt": snapshot_dt,
        "snapshot_time": snapshot_dt.isoformat(),
        "source_path": str(path),
        "items": items,
    }


def load_codex_history_items(session_paths=None, archived_paths=None):
    try:
        if session_paths is None:
            session_paths = list_codex_history_paths(CODEX_SESSIONS_ROOT, recursive=True)
        else:
            session_paths = [Path(path) for path in session_paths]

        if archived_paths is None:
            archived_paths = list_codex_history_paths(CODEX_ARCHIVED_SESSIONS_ROOT, recursive=False)
        else:
            archived_paths = [Path(path) for path in archived_paths]
    except OSError as exc:
        return make_provider_result(
            "unreadable",
            reason=f"Unable to discover Codex history: {exc}",
        )

    candidate_paths = session_paths + archived_paths
    if not candidate_paths:
        return make_provider_result(
            "missing",
            reason="No Codex history files found.",
        )

    newest_snapshot = None
    unreadable_error = None
    for path in candidate_paths:
        try:
            for record in iter_jsonl_objects(path):
                snapshot = extract_codex_snapshot(path, record)
                if snapshot is None:
                    continue
                if newest_snapshot is None or snapshot["snapshot_dt"] > newest_snapshot["snapshot_dt"]:
                    newest_snapshot = snapshot
        except OSError as exc:
            if unreadable_error is None:
                unreadable_error = exc
            continue

    if unreadable_error is not None:
        return make_provider_result(
            "unreadable",
            reason=f"Unable to read Codex history: {unreadable_error}",
        )

    if newest_snapshot is None:
        return make_provider_result(
            "unavailable",
            reason="No Codex rate limit snapshots found.",
        )

    return make_provider_result(
        "ok",
        snapshot_time=newest_snapshot["snapshot_time"],
        source_path=newest_snapshot["source_path"],
        cacheable=True,
        items=newest_snapshot["items"],
    )

def send_notification(title, message):
    """macOS 通知センターに通知を送る。"""
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{message}" with title "{title}"'],
            timeout=5, capture_output=True,
        )
    except Exception:
        pass

def check_and_notify(items, config):
    """予測使用率が閾値を超えたら通知を送る（リセットサイクルごとに1回）。"""
    state = load_alert_state()
    changed = False

    for item in items:
        proj = item["projected"]
        if proj is None:
            continue

        resets_at = item["resets_at_raw"] or ""
        key   = item["key"]
        label = item["label_jp"]
        alert_key = f"{key}_alert"
        warn_key  = f"{key}_warn"

        if proj >= config["alert_pct"] and state.get(alert_key) != resets_at:
            send_notification(
                "Claude Usage 🔴",
                f"{label}の予測使用率が {proj:.0f}% に達します（上限超過）",
            )
            state[alert_key] = resets_at
            state[warn_key]  = resets_at  # warn も同時にマーク（重複送信防止）
            changed = True
        elif proj >= config["warn_pct"] and state.get(warn_key) != resets_at:
            send_notification(
                "Claude Usage 🟡",
                f"{label}の予測使用率が {proj:.0f}% に達します",
            )
            state[warn_key] = resets_at
            changed = True

    if changed:
        save_alert_state(state)

# ── browser モード: Cookie 取得 ────────────────────────────
def get_session(cookie_jar):
    s = requests.Session()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": "https://claude.ai/settings/usage",
    }
    s.headers.update(headers)
    for c in cookie_jar:
        s.cookies.set(c.name, c.value, domain=c.domain)
    return s

def get_org_uuid(session):
    r = session.get(f"{BASE_URL}/api/organizations", timeout=10)
    r.raise_for_status()
    orgs = r.json()
    if not orgs:
        raise RuntimeError("組織が見つかりません")
    return orgs[0]["uuid"]

def get_usage(session, org_uuid):
    r = session.get(f"{BASE_URL}/api/organizations/{org_uuid}/usage", timeout=10)
    r.raise_for_status()
    return r.json()

def fetch_usage_browser():
    """browser_cookie3 経由で chrome.ai API からクォータ情報を取得する。"""
    if not HAS_BROWSER_COOKIE3:
        raise RuntimeError(
            "browser_cookie3 がインストールされていません。"
            "「pip3 install browser-cookie3」を実行するか、"
            "data_source を \"oauth\" に変更してください。"
        )
    cookie_jar = browser_cookie3.chrome(domain_name=".claude.ai")
    session = get_session(cookie_jar)
    org_uuid = get_org_uuid(session)
    return get_usage(session, org_uuid)

# ── oauth モード: macOS Keychain トークン ─────────────────
def get_oauth_token():
    """macOS Keychain から Claude Code OAuth アクセストークンを取得する。"""
    result = subprocess.run(
        ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
        capture_output=True, text=True, timeout=5,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Keychain に Claude Code-credentials が見つかりません。"
            "Claude Code にログインしているか確認してください。"
        )
    data = json.loads(result.stdout.strip())
    token = data.get("claudeAiOauth", {}).get("accessToken", "")
    if not token:
        raise RuntimeError("OAuth アクセストークンが空です。Claude Code を再ログインしてください。")
    return token

def fetch_usage_oauth():
    """macOS Keychain の OAuth トークンで api.anthropic.com からクォータ情報を取得する。"""
    token = get_oauth_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": "claude-code/2.0.32",
        "Accept": "application/json",
    }
    r = requests.get(OAUTH_API_URL, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()

# ── 表示ヘルパー ─────────────────────────────────────────────
def pct_color(pct):
    if pct >= 85: return "red"
    if pct >= 60: return "orange"
    return "green"

def progress_bar(pct, projected=None, width=12):
    current = round(pct / 100 * width)
    if projected and projected > 100:
        overflow_chars = round((projected - 100) / 100 * width)
        proj_within = width - current  # current〜100% の ▒ 部分
        return "█" * current + "▒" * proj_within + "▓" * overflow_chars
    proj = round(min(projected or pct, 100) / 100 * width) if projected else current
    return "█" * current + "▒" * (proj - current) + "░" * (width - proj)

def calc_projected(pct, resets_at_str, window_hours):
    """現在のペースでウィンドウ終了時に到達する予測使用率を返す。計算不能時は None。

    now, resets_at, utilization, window_hours の4値のみで計算:
      elapsed       = window_hours - time_remaining
      burn_rate     = pct / elapsed
      projected     = burn_rate * window_hours
    """
    if not resets_at_str or pct < 2:
        return None
    try:
        resets_at = datetime.fromisoformat(resets_at_str)
        now = datetime.now(timezone.utc)
        time_remaining_h = (resets_at - now).total_seconds() / 3600
        time_elapsed_h = window_hours - time_remaining_h
        if time_elapsed_h < 0.05:   # 開始直後は計算しない（ゼロ除算防止）
            return None
        burn_rate = pct / time_elapsed_h        # %/hour
        return burn_rate * window_hours          # ウィンドウ終了時の予測値
    except Exception:
        return None

def calc_exhaust_info(pct, projected, resets_at_str, window_hours):
    """7d全消化ガイド: 残りクオータを消化するための目標ペース情報を計算。

    Returns dict or None:
      - multiplier:     現ペースの何倍必要か (projected > 0 の場合)
      - target_per_5h:  5時間あたり消費すべき % (当該クオータ基準)
      - remaining_pct:  残り %
      - sessions_left:  残りの5時間セッション数
    """
    if not resets_at_str or window_hours < 24:   # 5hクオータは対象外
        return None
    try:
        resets_at = datetime.fromisoformat(resets_at_str)
        now = datetime.now(timezone.utc)
        time_remaining_h = (resets_at - now).total_seconds() / 3600
        if time_remaining_h <= 0:
            return None
        remaining_pct = 100 - pct
        if remaining_pct <= 0:
            return {"multiplier": 0, "target_per_5h": 0,
                    "remaining_pct": 0, "sessions_left": 0}
        sessions_left = time_remaining_h / 5
        target_per_5h = remaining_pct / sessions_left
        multiplier = round(100 / projected, 1) if projected and projected > 0 else None
        return {
            "multiplier": multiplier,
            "target_per_5h": target_per_5h,
            "remaining_pct": remaining_pct,
            "sessions_left": sessions_left,
        }
    except Exception:
        return None

def burn_icon(projected, config):
    """burn rate 予測値からアイコン絵文字を返す。"""
    if projected is None:                         return "🟢"
    if projected >= config["alert_pct"]:          return "🔴"
    if projected >= config["warn_pct"]:           return "🟠"
    if projected >= config["caution_pct"]:        return "🟡"
    return "🟢"

def format_reset(resets_at_str):
    """resets_at → '3時間12分後' または '水 21:00' 形式"""
    if not resets_at_str:
        return ""
    try:
        resets_at = datetime.fromisoformat(resets_at_str)
        now = datetime.now(timezone.utc)
        delta = resets_at - now
        total_seconds = int(delta.total_seconds())
        if total_seconds <= 0:
            return "まもなくリセット"
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        if hours >= 24:
            day_names = ["月", "火", "水", "木", "金", "土", "日"]
            local = resets_at.astimezone()
            return f"{day_names[local.weekday()]} {local.strftime('%H:%M')} にリセット"
        if hours > 0:
            return f"{hours}時間{minutes}分後にリセット"
        return f"{minutes}分後にリセット"
    except Exception:
        return ""


def render_config_error(message):
    print("⚠️ Claude Usage")
    print("---")
    print(f"設定エラー: {message}")

# ── メイン ───────────────────────────────────────────────────
def main():
    try:
        config = normalize_provider_config(dict(load_config()))
    except RuntimeError as e:
        render_config_error(str(e))
        return

    provider = config["provider"]
    if provider != "codex":
        render_config_error(f"provider not yet supported: {provider}")
        return

    # config["metrics"] の順序でフィルタリング
    enabled_keys = config["metrics"]
    metrics = [(k, le, lj, wh) for k, le, lj, wh in ALL_METRICS if k in enabled_keys]

    data_source = config.get("data_source", "browser")

    try:
        if data_source == "oauth":
            usage = fetch_usage_oauth()
        else:
            usage = fetch_usage_browser()
    except requests.exceptions.ConnectionError:
        cached = load_cache(provider)
        if cached:
            render_output(cached["items"], config, stale_reason="オフライン（前回の値を表示中）")
        else:
            print("📵 Claude  |  color=gray")
            print("---")
            print("オフライン  |  color=gray")
        return
    except requests.exceptions.Timeout:
        cached = load_cache(provider)
        if cached:
            render_output(cached["items"], config, stale_reason="タイムアウト（前回の値を表示中）")
        else:
            print("⏳ Claude  |  color=gray")
            print("---")
            print("タイムアウト  |  color=gray")
            print("↺ 再試行  |  refresh=true")
        return
    except requests.exceptions.HTTPError as e:
        cached = load_cache(provider)
        status = e.response.status_code
        if status in (401, 403):
            if data_source == "oauth":
                reason = "トークン期限切れ（前回の値を表示中）"
            else:
                reason = "ログインが必要です（前回の値を表示中）"
        else:
            reason = f"HTTPエラー {status}（前回の値を表示中）"
        if cached:
            render_output(cached["items"], config, stale_reason=reason)
        else:
            if status in (401, 403):
                print("🔑 Claude  |  color=gray")
                print("---")
                if data_source == "oauth":
                    print("トークン期限切れ  |  color=red")
                    print("Claude Code を再ログインしてください  |  color=gray size=11")
                else:
                    print("ログインが必要です  |  color=red")
                    print("claude.ai を開く  |  href=https://claude.ai/settings/usage")
            else:
                print("⚠️ Claude  |  color=gray")
                print("---")
                print(f"HTTPエラー: {status}  |  color=red")
        return
    except Exception as e:
        cached = load_cache(provider)
        if cached:
            render_output(cached["items"], config, stale_reason=f"エラー（前回の値を表示中）")
        else:
            print("⚠️ Claude Usage")
            print("---")
            print(f"エラー: {str(e)[:120]}")
            print("---")
            print("設定ページを開く | href=https://claude.ai/settings/usage")
        return

    # 有効な指標だけ抽出し、各自の burn rate 予測も計算
    items = []
    for key, label_en, label_jp, window_hours in metrics:
        data = usage.get(key)
        if data is None:
            continue
        pct = int(data.get("utilization", 0))
        resets_at = data.get("resets_at")
        proj = calc_projected(pct, resets_at, window_hours)
        items.append({
            "key":          key,
            "label_en":     label_en,
            "label_jp":     label_jp,
            "window_hours": window_hours,
            "pct":          pct,
            "projected":    proj,
            "reset":        format_reset(resets_at),
            "resets_at_raw": resets_at,
            "exhaust_info": calc_exhaust_info(pct, proj, resets_at, window_hours),
        })

    if not items:
        print("⚠️ Claude Usage")
        print("---")
        print("データなし（ログインが必要かもしれません）")
        print("設定ページを開く | href=https://claude.ai/settings/usage")
        return

    # キャッシュに保存（次回エラー時のフォールバック用）
    save_cache(provider, {
        "status": "ok",
        "reason": "",
        "snapshot_time": None,
        "source_path": None,
        "cacheable": True,
        "items": items,
    })

    # 通知チェック（閾値超過時のみ macOS 通知を送信）
    check_and_notify(items, config)

    render_output(items, config)


def render_output(items, config, stale_reason=None):
    """メニューバーとドロップダウンを描画する。
    stale_reason が指定されていればキャッシュ表示であることを示す。
    """
    # ── メニューバー タイトル ──────────────────────────────────
    # 5h はフル表示、7d 系は悪い方のアイコンのみ（詳細はドロップダウン）
    _icon_severity = {"🟢": 0, "🟡": 1, "🟠": 2, "🔴": 3}
    bar_parts = []
    worst_7d_icon = None
    for i in items:
        icon = burn_icon(i["projected"], config)
        if i["window_hours"] < 24:
            bar_parts.append(f"{icon} {i['pct']}%")
        else:
            if worst_7d_icon is None or _icon_severity.get(icon, 0) > _icon_severity.get(worst_7d_icon, 0):
                worst_7d_icon = icon
    if worst_7d_icon is not None:
        bar_parts.append(worst_7d_icon)
    bar_title = " ".join(bar_parts)
    if stale_reason:
        bar_title = f"⚠️ {bar_title}"
    print(bar_title)

    # ── ドロップダウン ────────────────────────────────────────
    print("---")
    if stale_reason:
        print(f"⚠️ {stale_reason}  |  color=red size=11")
        print("claude.ai を開く  |  href=https://claude.ai/settings/usage")
        print("---")

    # 5h セクション用: 7d全消化目標を算出
    seven_day_mult = None
    for i in items:
        info = i.get("exhaust_info")
        if info and info.get("multiplier") is not None:
            seven_day_mult = info["multiplier"]
            break  # metrics 定義順で最初の 7d を採用

    for item in items:
        proj = item["projected"]
        icon = burn_icon(proj, config)
        c    = pct_color(item["pct"])
        wh = item["window_hours"]
        window_label = f"{wh}h" if wh < 24 else f"{wh // 24}d"

        # 5h セクションのみ: 7d全消化目標
        # 表示条件: 5h予測 < 100%（利用不可リスクなし）かつ目標 < 予測（達成圏内）
        target_5h = None
        if wh < 24 and seven_day_mult is not None and proj is not None and proj < 100:
            candidate = round(proj * seven_day_mult, 1)
            if candidate < proj:
                target_5h = candidate

        bar = progress_bar(item["pct"], proj, width=config["bar_width"])

        print(f"{icon} {item['label_jp']}  |  color={c}")

        # バーラベル
        if target_5h is not None:
            bar_label = f"{item['pct']}%→{proj:.0f}% 🎯{target_5h:.0f}%"
        elif proj is not None:
            bar_label = f"{item['pct']}% → {proj:.0f}%"
        else:
            bar_label = f"{item['pct']}%"

        print(f"   {bar} {bar_label}  |  font=Menlo size=12 color={c}")
        if proj is not None:
            proj_color = (
                "red"    if proj >= config["alert_pct"]   else
                "orange" if proj >= config["warn_pct"]    else
                "yellow" if proj >= config["caution_pct"] else
                "gray"
            )
            print(f"   📈 {window_label}予測: {proj:.0f}%  |  size=11 color={proj_color}")
        if item["reset"]:
            print(f"   🔄 {item['reset']}  |  size=11 color=gray")
        print("---")

    print("↗ claude.ai/settings/usage  |  href=https://claude.ai/settings/usage")
    print("↺ 今すぐ更新  |  refresh=true")


if __name__ == "__main__":
    main()
