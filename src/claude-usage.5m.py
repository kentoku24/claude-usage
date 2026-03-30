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
echo "⚠️ Codex | color=gray"
echo "---"
echo "pip3 install requests (Python 3.10+)"
exit
'''
#
# <xbar.title>Codex Usage</xbar.title>
# <xbar.version>v2.1</xbar.version>
# <xbar.author>kmatsunami</xbar.author>
# <xbar.desc>Codex の使用量をメニューバーに表示</xbar.desc>
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
#   ~/.codex-usage-config.json を作成して設定を上書き可能
#   例: {"warn_pct": 70, "alert_pct": 90, "bar_width": 16}

import sys
import json
import re
import os
import html as html_lib
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("⚠️ Codex Usage")
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

PRODUCT_NAME = "Codex"
USAGE_URL = "https://chatgpt.com/codex/settings/usage"
CODEX_API_URL = "https://chatgpt.com/backend-api/wham/usage"
CODEX_AUTH_ENDPOINT = "https://auth.openai.com/oauth/token"
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_REFRESH_DAYS = 8

CODEX_AUTH_PATHS = [
    Path.home() / ".codex" / "auth.json",
    Path.home() / ".config" / "codex" / "auth.json",
]

CONFIG_PATHS = [
    Path.home() / ".codex-usage-config.json",
    Path.home() / ".claude-usage-config.json",
]
ALERT_STATE_PATHS = [
    Path.home() / ".codex-usage-alerted.json",
    Path.home() / ".claude-usage-alerted.json",
]
CACHE_PATHS = [
    Path.home() / ".codex-usage-cache.json",
    Path.home() / ".claude-usage-cache.json",
]

DEFAULT_CONFIG = {
    "caution_pct": 60,  # 予測使用率の注意閾値（🟡）
    "warn_pct":    80,  # 予測使用率の警告閾値（🟠）
    "alert_pct":  100,  # 予測使用率のアラート閾値（🔴）
    "bar_width": 12,    # プログレスバーの幅（文字数）
    "metrics": [],      # 空なら取得できた全指標を表示
    # データ取得方式: "oauth"（Codex auth.json + backend-api/wham/usage）
    #               "browser"（OpenAI dashboard の HTML を解析）
    "data_source": "oauth",
}

def first_existing_path(paths):
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


# ── 設定ロード ───────────────────────────────────────────────
def load_config():
    config = dict(DEFAULT_CONFIG)
    path = first_existing_path(CONFIG_PATHS)
    if path.exists():
        try:
            user = read_json(path)
            for k, v in user.items():
                if k in DEFAULT_CONFIG:
                    config[k] = v
        except Exception:
            pass  # 読み込み失敗時はデフォルト値を使用
    return config

# ── 通知アラート ─────────────────────────────────────────────
def load_alert_state():
    """送信済みアラートの状態を読み込む。"""
    path = first_existing_path(ALERT_STATE_PATHS)
    if path.exists():
        try:
            return read_json(path)
        except Exception:
            pass
    return {}

def save_alert_state(state):
    try:
        write_json(ALERT_STATE_PATHS[0], state)
    except Exception:
        pass

# ── 前回値キャッシュ ──────────────────────────────────────────
def save_cache(items):
    """正常取得時の items をキャッシュに保存する。"""
    try:
        write_json(CACHE_PATHS[0], items)
    except Exception:
        pass

def load_cache():
    """前回の items をキャッシュから読み込む。なければ None。"""
    path = first_existing_path(CACHE_PATHS)
    if path.exists():
        try:
            return read_json(path)
        except Exception:
            pass
    return None

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
                f"{PRODUCT_NAME} Usage 🔴",
                f"{label}の予測使用率が {proj:.0f}% に達します（上限超過）",
            )
            state[alert_key] = resets_at
            state[warn_key]  = resets_at  # warn も同時にマーク（重複送信防止）
            changed = True
        elif proj >= config["warn_pct"] and state.get(warn_key) != resets_at:
            send_notification(
                f"{PRODUCT_NAME} Usage 🟡",
                f"{label}の予測使用率が {proj:.0f}% に達します",
            )
            state[warn_key] = resets_at
            changed = True

    if changed:
        save_alert_state(state)

# ── Codex: 取得とパース ────────────────────────────────────
def get_session(cookie_jar, referer=USAGE_URL):
    s = requests.Session()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Content-Type": "application/json",
        "Referer": referer,
    }
    s.headers.update(headers)
    for c in cookie_jar:
        s.cookies.set(c.name, c.value, domain=c.domain)
    return s

def _browser_cookie_jar():
    if not HAS_BROWSER_COOKIE3:
        raise RuntimeError(
            "browser_cookie3 がインストールされていません。"
            "「pip3 install browser-cookie3」を実行してください。"
        )
    last_error = None
    for domain in (".chatgpt.com", "chatgpt.com", ".openai.com"):
        try:
            return browser_cookie3.chrome(domain_name=domain)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"ChatGPT Cookie を取得できません: {last_error}")

def _find_json_scripts(html_text):
    patterns = [
        r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        r'<script[^>]+type="application/json"[^>]*>(.*?)</script>',
    ]
    blobs = []
    for pattern in patterns:
        for match in re.finditer(pattern, html_text, flags=re.IGNORECASE | re.DOTALL):
            text = html_lib.unescape(match.group(1)).strip()
            if text and text not in blobs:
                blobs.append(text)
    return blobs

def _walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)

def _infer_window_hours(candidate):
    for key in ("window_hours", "period_hours", "cycle_hours", "duration_hours", "interval_hours"):
        raw = candidate.get(key)
        if isinstance(raw, (int, float)) and raw > 0:
            return int(raw) if float(raw).is_integer() else float(raw)
    raw_seconds = candidate.get("limit_window_seconds")
    if isinstance(raw_seconds, (int, float)) and raw_seconds > 0:
        hours = raw_seconds / 3600
        return int(hours) if float(hours).is_integer() else hours
    text = " ".join(
        str(candidate.get(key, ""))
        for key in ("key", "name", "slug", "label", "title", "description")
    ).lower()
    if any(term in text for term in ("5h", "5-hour", "5 hour", "five hour", "session")):
        return 5
    if any(term in text for term in ("weekly", "7d", "7-day", "7 day", "week", "all")):
        return 168
    return 168

def _normalize_usage_candidate(candidate, fallback_index):
    raw_pct = candidate.get("utilization")
    if raw_pct is None:
        raw_pct = candidate.get("percentage")
    if raw_pct is None:
        raw_pct = candidate.get("usage")
    if raw_pct is None:
        return None

    try:
        pct = int(float(raw_pct))
    except Exception:
        return None

    resets_at = (
        candidate.get("resets_at")
        or candidate.get("reset_at")
        or candidate.get("resetsAt")
        or candidate.get("resetAt")
    )
    key = (
        candidate.get("key")
        or candidate.get("id")
        or candidate.get("slug")
        or candidate.get("name")
        or f"usage_{fallback_index}"
    )
    label = (
        candidate.get("label")
        or candidate.get("title")
        or candidate.get("name")
        or str(key)
    )
    window_hours = _infer_window_hours(candidate)
    return {
        "key": str(key),
        "label_en": str(label),
        "label_jp": str(label),
        "window_hours": window_hours,
        "pct": pct,
        "projected": None,
        "reset": "",
        "resets_at_raw": resets_at,
        "exhaust_info": None,
    }

def extract_usage_items_from_html(html_text):
    """Codex usage ページの HTML から usage アイテムを抽出する。"""
    items = []
    seen = set()
    for blob in _find_json_scripts(html_text):
        try:
            payload = json.loads(blob)
        except Exception:
            continue
        for idx, candidate in enumerate(_walk_json(payload)):
            if not isinstance(candidate, dict):
                continue
            if "utilization" not in candidate and "percentage" not in candidate and "usage" not in candidate:
                continue
            item = _normalize_usage_candidate(candidate, idx)
            if not item:
                continue
            signature = (
                item["key"],
                item["pct"],
                item["resets_at_raw"],
                item["window_hours"],
                item["label_jp"],
            )
            if signature in seen:
                continue
            seen.add(signature)
            items.append(item)
    items.sort(key=lambda item: (item["window_hours"], item["label_jp"]))
    return items

def fetch_usage_browser():
    """ChatGPT の usage ページ HTML をブラウザ Cookie で取得する。"""
    cookie_jar = _browser_cookie_jar()
    session = get_session(cookie_jar)
    r = session.get(USAGE_URL, timeout=10)
    r.raise_for_status()
    items = extract_usage_items_from_html(r.text)
    if not items:
        raise RuntimeError("usage ページからデータを抽出できませんでした")
    return items

def _parse_token_payload(raw_text):
    raw_text = raw_text.strip()
    if not raw_text:
        return {}
    try:
        data = json.loads(raw_text)
    except Exception:
        return {"access_token": raw_text}
    if isinstance(data, str):
        return {"access_token": data}
    if isinstance(data, dict):
        return data
    return {}

def codex_auth_paths():
    paths = []
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        paths.append(Path(codex_home) / "auth.json")
    paths.extend(CODEX_AUTH_PATHS)
    return paths

def find_codex_auth_file():
    return first_existing_path(codex_auth_paths())

def load_codex_auth():
    path = find_codex_auth_file()
    if not path.exists():
        raise RuntimeError(
            "Codex の auth.json が見つかりません。"
            "Codex にログインして ~/.codex/auth.json を作成してください。"
        )
    try:
        return path, read_json(path)
    except Exception as exc:
        raise RuntimeError(f"Codex auth.json を読めません: {exc}") from exc

def _nested_get(data, *keys):
    cursor = data
    for key in keys:
        if not isinstance(cursor, dict) or key not in cursor:
            return None
        cursor = cursor[key]
    return cursor

def _extract_access_token(auth):
    for path in [
        ("tokens", "access_token"),
        ("tokens", "accessToken"),
        ("access_token",),
        ("accessToken",),
        ("access", "token"),
    ]:
        token = _nested_get(auth, *path)
        if isinstance(token, str) and token.strip():
            return token.strip()
    return ""

def _extract_refresh_token(auth):
    for path in [
        ("tokens", "refresh_token"),
        ("tokens", "refreshToken"),
        ("refresh_token",),
        ("refreshToken",),
    ]:
        token = _nested_get(auth, *path)
        if isinstance(token, str) and token.strip():
            return token.strip()
    return ""

def _extract_last_refresh(auth):
    value = auth.get("last_refresh") if isinstance(auth, dict) else None
    return value if isinstance(value, str) else ""

def codex_needs_refresh(auth):
    last_refresh = _extract_last_refresh(auth)
    if not last_refresh:
        return True
    try:
        last_ts = datetime.fromisoformat(last_refresh.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - last_ts).days >= CODEX_REFRESH_DAYS
    except Exception:
        return True

def refresh_codex_token(refresh_token):
    clean_token = refresh_token.split("|", 1)[0].strip()
    response = requests.post(
        CODEX_AUTH_ENDPOINT,
        headers={"Content-Type": "application/json"},
        json={
            "client_id": CODEX_CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": clean_token,
            "scope": "openid profile email",
        },
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError(payload.get("error_description") or payload["error"])
    return payload

def persist_codex_auth(path, auth, token_payload):
    updated = dict(auth)
    tokens = dict(updated.get("tokens") or {})
    if token_payload.get("access_token"):
        tokens["access_token"] = token_payload["access_token"]
    if token_payload.get("refresh_token"):
        tokens["refresh_token"] = token_payload["refresh_token"]
    if token_payload.get("id_token"):
        tokens["id_token"] = token_payload["id_token"]
    updated["tokens"] = tokens
    updated["last_refresh"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_json(path, updated)

def _window_label(window_key, candidate):
    text = " ".join(
        str(candidate.get(key, ""))
        for key in ("name", "label", "title", "description", "window_name")
    ).lower()
    if window_key == "primary_window" or "5-hour" in text or "5 hour" in text or "5h" in text:
        return "現在のセッション", "5-hour limit", 5
    if window_key == "secondary_window" or "weekly" in text or "week" in text or "7d" in text:
        return "すべてのモデル", "Weekly limit", 168
    if "code review" in text or "review" in text:
        return "Code review", "Code review limit", 168
    return str(candidate.get("label") or candidate.get("title") or window_key), str(window_key), _infer_window_hours(candidate)

def _pct_from_candidate(candidate):
    for key in ("used_percent", "utilization", "percentage", "usage"):
        raw = candidate.get(key)
        if raw is None:
            continue
        try:
            return int(round(float(raw)))
        except Exception:
            continue
    remaining = candidate.get("remainingFraction") or candidate.get("remaining_fraction")
    if remaining is None:
        return None
    try:
        return int(round((1 - float(remaining)) * 100))
    except Exception:
        return None

def _resets_from_candidate(candidate):
    for key in ("resets_at", "reset_at", "resetAt", "reset_at_raw", "reset_time"):
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)) and value > 0:
            return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    reset_after = candidate.get("reset_after_seconds")
    if isinstance(reset_after, (int, float)) and reset_after > 0:
        return (datetime.now(timezone.utc) + timedelta(seconds=reset_after)).isoformat()
    return ""

def _item_from_window(window_key, candidate):
    pct = _pct_from_candidate(candidate)
    if pct is None:
        return None
    label_jp, label_en, window_hours = _window_label(window_key, candidate)
    return {
        "key": window_key,
        "label_en": label_en,
        "label_jp": label_jp,
        "window_hours": window_hours,
        "pct": pct,
        "projected": None,
        "reset": "",
        "resets_at_raw": _resets_from_candidate(candidate),
        "exhaust_info": None,
    }

def extract_usage_items_from_codex_payload(payload):
    """Codex API の JSON から usage アイテムを抽出する。"""
    if not isinstance(payload, dict):
        return []

    items = []
    seen = set()

    rate_limit = payload.get("rate_limit") or payload.get("rateLimit")
    if isinstance(rate_limit, dict):
        for window_key in ("primary_window", "secondary_window", "code_review_window"):
            candidate = rate_limit.get(window_key)
            if isinstance(candidate, dict):
                item = _item_from_window(window_key, candidate)
                if item:
                    sig = (item["key"], item["pct"], item["resets_at_raw"], item["window_hours"])
                    if sig not in seen:
                        seen.add(sig)
                        items.append(item)

    if not items:
        for candidate in _walk_json(payload):
            if not isinstance(candidate, dict):
                continue
            item = _item_from_window(
                str(candidate.get("window_key") or candidate.get("key") or candidate.get("name") or "usage"),
                candidate,
            )
            if item:
                sig = (item["key"], item["pct"], item["resets_at_raw"], item["window_hours"])
                if sig not in seen:
                    seen.add(sig)
                    items.append(item)

    items.sort(key=lambda item: (item["window_hours"], item["label_jp"]))
    return items

def fetch_usage_oauth():
    """Codex auth.json の OAuth トークンで backend-api/wham/usage を取得する。"""
    path, auth = load_codex_auth()
    refresh_token = _extract_refresh_token(auth)
    if refresh_token and codex_needs_refresh(auth):
        try:
            token_payload = refresh_codex_token(refresh_token)
            persist_codex_auth(path, auth, token_payload)
            auth = read_json(path)
        except Exception:
            pass

    access_token = _extract_access_token(auth)
    if not access_token:
        raise RuntimeError(
            "Codex auth.json に access_token がありません。"
            "Codex で再ログインしてください。"
        )

    response = requests.get(
        CODEX_API_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        timeout=10,
    )
    response.raise_for_status()
    items = extract_usage_items_from_codex_payload(response.json())
    if not items:
        raise RuntimeError("Codex usage API からデータを抽出できませんでした")
    return items

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

# ── メイン ───────────────────────────────────────────────────
def main():
    config = load_config()

    data_source = config.get("data_source", "oauth")

    try:
        if data_source == "oauth":
            usage = fetch_usage_oauth()
        else:
            usage = fetch_usage_browser()
    except requests.exceptions.ConnectionError:
        cached = load_cache()
        if cached:
            render_output(cached, config, stale_reason="オフライン（前回の値を表示中）")
        else:
            print(f"📵 {PRODUCT_NAME}  |  color=gray")
            print("---")
            print("オフライン  |  color=gray")
        return
    except requests.exceptions.Timeout:
        cached = load_cache()
        if cached:
            render_output(cached, config, stale_reason="タイムアウト（前回の値を表示中）")
        else:
            print(f"⏳ {PRODUCT_NAME}  |  color=gray")
            print("---")
            print("タイムアウト  |  color=gray")
            print("↺ 再試行  |  refresh=true")
        return
    except requests.exceptions.HTTPError as e:
        cached = load_cache()
        status = e.response.status_code
        if status in (401, 403):
            if data_source == "oauth":
                reason = "トークン期限切れ（前回の値を表示中）"
            else:
                reason = "ログインが必要です（前回の値を表示中）"
        else:
            reason = f"HTTPエラー {status}（前回の値を表示中）"
        if cached:
            render_output(cached, config, stale_reason=reason)
        else:
            if status in (401, 403):
                print(f"🔑 {PRODUCT_NAME}  |  color=gray")
                print("---")
                if data_source == "oauth":
                    print("トークン期限切れ  |  color=red")
                    print("ChatGPT へ再ログインしてください  |  color=gray size=11")
                else:
                    print("ログインが必要です  |  color=red")
                    print(f"{USAGE_URL} を開く  |  href={USAGE_URL}")
            else:
                print(f"⚠️ {PRODUCT_NAME}  |  color=gray")
                print("---")
                print(f"HTTPエラー: {status}  |  color=red")
        return
    except Exception as e:
        cached = load_cache()
        if cached:
            render_output(cached, config, stale_reason=f"エラー（前回の値を表示中）")
        else:
            print(f"⚠️ {PRODUCT_NAME} Usage")
            print("---")
            print(f"エラー: {str(e)[:120]}")
            print("---")
            print(f"設定ページを開く | href={USAGE_URL}")
        return

    items = usage
    enabled_keys = [str(key) for key in config.get("metrics", []) if key]
    if enabled_keys:
        filtered = [item for item in items if item.get("key") in enabled_keys]
        if filtered:
            items = filtered

    if not items:
        print(f"⚠️ {PRODUCT_NAME} Usage")
        print("---")
        print("データなし（ログインが必要かもしれません）")
        print(f"設定ページを開く | href={USAGE_URL}")
        return

    # 各自の burn rate 予測を計算
    normalized_items = []
    for item in items:
        pct = int(item.get("pct", 0))
        resets_at = item.get("resets_at_raw")
        window_hours = item.get("window_hours", 168)
        proj = calc_projected(pct, resets_at, window_hours)
        normalized = dict(item)
        normalized.update({
            "projected": proj,
            "reset": format_reset(resets_at),
            "exhaust_info": calc_exhaust_info(pct, proj, resets_at, window_hours),
        })
        normalized_items.append(normalized)
    items = normalized_items

    # キャッシュに保存（次回エラー時のフォールバック用）
    save_cache(items)

    # 通知チェック（閾値超過時のみ macOS 通知を送信）
    check_and_notify(items, config)

    render_output(items, config)


def render_output(items, config, stale_reason=None):
    """メニューバーとドロップダウンを描画する。
    stale_reason が指定されていればキャッシュ表示であることを示す。
    """
    # ── メニューバー タイトル ──────────────────────────────────
    _icon_severity = {"🟢": 0, "🟡": 1, "🟠": 2, "🔴": 3}
    bar_parts = []
    worst_icon = None
    for i in items:
        icon = burn_icon(i["projected"], config)
        bar_parts.append(f"{icon} {i['pct']}%")
        if worst_icon is None or _icon_severity.get(icon, 0) > _icon_severity.get(worst_icon, 0):
            worst_icon = icon
    bar_title = " ".join(bar_parts)
    if stale_reason:
        bar_title = f"⚠️ {bar_title}"
    print(bar_title)

    # ── ドロップダウン ────────────────────────────────────────
    print("---")
    if stale_reason:
        print(f"⚠️ {stale_reason}  |  color=red size=11")
        print(f"{PRODUCT_NAME} の usage を開く  |  href={USAGE_URL}")
        print("---")

    for item in items:
        proj = item["projected"]
        icon = burn_icon(proj, config)
        c    = pct_color(item["pct"])
        wh = item["window_hours"]
        window_label = f"{wh}h" if wh < 24 else f"{wh // 24}d"

        bar = progress_bar(item["pct"], proj, width=config["bar_width"])

        print(f"{icon} {item['label_jp']}  |  color={c}")

        # バーラベル
        if proj is not None:
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

    print(f"↗ {USAGE_URL}  |  href={USAGE_URL}")
    print("↺ 今すぐ更新  |  refresh=true")


if __name__ == "__main__":
    main()
