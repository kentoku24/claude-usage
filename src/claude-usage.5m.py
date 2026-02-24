#!/bin/bash
# -*- coding: utf-8 -*-
''''true
# bash/python polyglot: Python 3.10+ with browser_cookie3 を自動検出
for py in $("$SHELL" -lc 'which -a python3' 2>/dev/null); do
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
# <xbar.version>v2.0</xbar.version>
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

import sys
from datetime import datetime, timezone

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

BASE_URL = "https://claude.ai"

# 画面表示の設定  (key, label_en, label_jp, window_hours)
METRICS = [
    ("five_hour",       "Session", "現在のセッション",   5),
    ("seven_day",       "All",     "すべてのモデル",    168),
    ("seven_day_sonnet","Sonnet",  "Sonnet のみ",      168),
]

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
    proj = round(min(projected or pct, 100) / 100 * width) if projected else current
    return "█" * current + "▒" * (proj - current) + "░" * (width - proj)

def calc_projected(pct, resets_at_str, window_hours):
    """現在のペースでウィンドウ終了時に到達する予測使用率を返す。
    計算不能な場合は None。"""
    if not resets_at_str or pct <= 0:
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

def burn_icon(projected):
    """burn rate 予測値からアイコン絵文字を返す。"""
    if projected is None:   return "🟢"
    if projected >= 100:    return "🔴"
    if projected >= 80:     return "🟡"
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
    try:
        cookie_jar = browser_cookie3.chrome(domain_name=".claude.ai")
        session = get_session(cookie_jar)
        org_uuid = get_org_uuid(session)
        usage = get_usage(session, org_uuid)
    except requests.exceptions.ConnectionError:
        print("📵 Claude  |  color=gray")
        print("---")
        print("オフライン  |  color=gray")
        return
    except requests.exceptions.Timeout:
        print("⏳ Claude  |  color=gray")
        print("---")
        print("タイムアウト  |  color=gray")
        print("↺ 再試行  |  refresh=true")
        return
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            print("🔑 Claude  |  color=gray")
            print("---")
            print("ログインが必要です  |  color=red")
            print("claude.ai を開く  |  href=https://claude.ai")
        else:
            print("⚠️ Claude  |  color=gray")
            print("---")
            print(f"HTTPエラー: {e.response.status_code}  |  color=red")
        return
    except Exception as e:
        print("⚠️ Claude Usage")
        print("---")
        print(f"エラー: {str(e)[:120]}")
        print("---")
        print("設定ページを開く | href=https://claude.ai/settings/usage")
        return

    # 有効な指標だけ抽出し、各自の burn rate 予測も計算
    items = []
    for key, label_en, label_jp, window_hours in METRICS:
        data = usage.get(key)
        if data is None:
            continue
        pct = int(data.get("utilization", 0))
        resets_at = data.get("resets_at")
        proj = calc_projected(pct, resets_at, window_hours)
        items.append({
            "key": key,
            "label_en": label_en,
            "label_jp": label_jp,
            "window_hours": window_hours,
            "pct": pct,
            "projected": proj,
            "reset": format_reset(resets_at),
        })

    if not items:
        print("⚠️ Claude Usage")
        print("---")
        print("データなし（ログインが必要かもしれません）")
        print("設定ページを開く | href=https://claude.ai/settings/usage")
        return

    # ── メニューバー タイトル ──────────────────────────────────
    bar_title = " ".join(f"{burn_icon(i['projected'])} {i['pct']}%" for i in items)
    print(bar_title)

    # ── ドロップダウン ────────────────────────────────────────
    print("---")
    for item in items:
        proj = item["projected"]
        icon = burn_icon(proj)
        c = pct_color(item["pct"])
        bar = progress_bar(item["pct"], proj)
        window_label = f"{item['window_hours']}h" if item["window_hours"] < 24 else f"{item['window_hours']//24}d"
        print(f"{icon} {item['label_jp']}: {item['pct']}%  |  color={c}")
        print(f"   {bar} {item['pct']}%  |  font=Menlo size=12 color={c}")
        if proj is not None:
            proj_color = "red" if proj >= 100 else "orange" if proj >= 80 else "gray"
            print(f"   📈 {window_label}予測: {proj:.0f}%  |  size=11 color={proj_color}")
        if item["reset"]:
            print(f"   🔄 {item['reset']}  |  size=11 color=gray")
        print("---")

    print("↗ claude.ai/settings/usage  |  href=https://claude.ai/settings/usage")
    print("↺ 今すぐ更新  |  refresh=true")


if __name__ == "__main__":
    main()
