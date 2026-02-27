#!/bin/bash
# -*- coding: utf-8 -*-
''''true
# bash/python polyglot: Python 3.10+ with browser_cookie3 を自動検出
for py in $("$SHELL" -lic 'which -a python3' 2>/dev/null); do
    "$py" -c 'import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)' 2>/dev/null || continue
    "$py" -c 'import browser_cookie3' 2>/dev/null || continue
    exec "$py" "$0"
done
echo "⚠️ Claude | color=gray"
echo "---"
echo "pip3 install browser-cookie3 requests (Python 3.10+)"
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
    import browser_cookie3
    import requests
except ImportError as e:
    missing = str(e).replace("No module named ", "").strip("'")
    print("⚠️ Claude Usage")
    print("---")
    print(f"依存ライブラリ不足: {missing}")
    print("ターミナルで実行してください | size=11 color=gray")
    print("pip3 install browser-cookie3 requests | bash=/bin/sh "
          "param1=-c param2='pip3 install browser-cookie3 requests' terminal=true")
    sys.exit(0)

BASE_URL        = "https://claude.ai"
CONFIG_PATH     = Path.home() / ".claude-usage-config.json"
ALERT_STATE_PATH = Path.home() / ".claude-usage-alerted.json"
CACHE_PATH      = Path.home() / ".claude-usage-cache.json"

# デフォルト設定（~/.claude-usage-config.json で上書き可能）
DEFAULT_CONFIG = {
    "caution_pct": 60,  # 予測使用率の注意閾値（🟡）
    "warn_pct":    80,  # 予測使用率の警告閾値（🟠）
    "alert_pct":  100,  # 予測使用率のアラート閾値（🔴）
    "bar_width": 12,    # プログレスバーの幅（文字数）
    "metrics": ["five_hour", "seven_day", "seven_day_sonnet"],  # 表示する指標
}

# 全指標の定義  (key, label_en, label_jp, window_hours)
ALL_METRICS = [
    ("five_hour",        "Session", "現在のセッション",   5),
    ("seven_day",        "All",     "すべてのモデル",    168),
    ("seven_day_sonnet", "Sonnet",  "Sonnet のみ",      168),
]

# ── 設定ロード ───────────────────────────────────────────────
def load_config():
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            user = json.loads(CONFIG_PATH.read_text())
            for k, v in user.items():
                if k in DEFAULT_CONFIG:
                    config[k] = v
        except Exception:
            pass  # 読み込み失敗時はデフォルト値を使用
    return config

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
def save_cache(items):
    """正常取得時の items をキャッシュに保存する。"""
    try:
        CACHE_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2))
    except Exception:
        pass

def load_cache():
    """前回の items をキャッシュから読み込む。なければ None。"""
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text())
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

# ── Cookie 取得 ─────────────────────────────────────────────
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

# ── API 呼び出し ────────────────────────────────────────────
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
    """現在のペースでウィンドウ終了時に到達する予測使用率を返す。

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

    # config["metrics"] の順序でフィルタリング
    enabled_keys = config["metrics"]
    metrics = [(k, le, lj, wh) for k, le, lj, wh in ALL_METRICS if k in enabled_keys]

    try:
        cookie_jar = browser_cookie3.chrome(domain_name=".claude.ai")
        session = get_session(cookie_jar)
        org_uuid = get_org_uuid(session)
        usage = get_usage(session, org_uuid)
    except requests.exceptions.ConnectionError:
        cached = load_cache()
        if cached:
            render_output(cached, config, stale_reason="オフライン（前回の値を表示中）")
        else:
            print("📵 Claude  |  color=gray")
            print("---")
            print("オフライン  |  color=gray")
        return
    except requests.exceptions.Timeout:
        cached = load_cache()
        if cached:
            render_output(cached, config, stale_reason="タイムアウト（前回の値を表示中）")
        else:
            print("⏳ Claude  |  color=gray")
            print("---")
            print("タイムアウト  |  color=gray")
            print("↺ 再試行  |  refresh=true")
        return
    except requests.exceptions.HTTPError as e:
        cached = load_cache()
        if e.response.status_code == 403:
            reason = "ログインが必要です（前回の値を表示中）"
        else:
            reason = f"HTTPエラー {e.response.status_code}（前回の値を表示中）"
        if cached:
            render_output(cached, config, stale_reason=reason)
        else:
            if e.response.status_code == 403:
                print("🔑 Claude  |  color=gray")
                print("---")
                print("ログインが必要です  |  color=red")
                print("claude.ai を開く  |  href=https://claude.ai/settings/usage")
            else:
                print("⚠️ Claude  |  color=gray")
                print("---")
                print(f"HTTPエラー: {e.response.status_code}  |  color=red")
        return
    except Exception as e:
        cached = load_cache()
        if cached:
            render_output(cached, config, stale_reason=f"エラー（前回の値を表示中）")
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
        })

    if not items:
        print("⚠️ Claude Usage")
        print("---")
        print("データなし（ログインが必要かもしれません）")
        print("設定ページを開く | href=https://claude.ai/settings/usage")
        return

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
    bar_title = " ".join(
        f"{burn_icon(i['projected'], config)} {i['pct']}%" for i in items
    )
    if stale_reason:
        bar_title = f"⚠️ {bar_title}"
    print(bar_title)

    # ── ドロップダウン ────────────────────────────────────────
    print("---")
    if stale_reason:
        print(f"⚠️ {stale_reason}  |  color=red size=11")
        print("claude.ai を開く  |  href=https://claude.ai/settings/usage")
        print("---")

    for item in items:
        proj = item["projected"]
        icon = burn_icon(proj, config)
        c    = pct_color(item["pct"])
        bar  = progress_bar(item["pct"], proj, width=config["bar_width"])
        wh = item["window_hours"]
        window_label = f"{wh}h" if wh < 24 else f"{wh // 24}d"
        print(f"{icon} {item['label_jp']}  |  color={c}")
        bar_label = f"{item['pct']}% → {proj:.0f}%" if proj is not None else f"{item['pct']}%"
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
