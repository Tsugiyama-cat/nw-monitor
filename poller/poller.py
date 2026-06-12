"""NW定期ポーリング (LLM不使用).

config/runtime.env と checks.yml を毎サイクル読み直すため、
GUIでトークンを更新しても再起動なしで反映される。
異常は data/anomalies.jsonl に追記し、Slack Webhookが設定されていれば通知する。
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

CONFIG_ENV = Path("/config/runtime.env")
CHECKS_FILE = Path("/app/checks.yml")
DATA_DIR = Path("/data")
STATUS_FILE = DATA_DIR / "status.json"
ANOMALY_FILE = DATA_DIR / "anomalies.jsonl"


def load_env() -> dict:
    env = {}
    if CONFIG_ENV.exists():
        for line in CONFIG_ENV.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def render(template: str, env: dict) -> str:
    out = template
    for k, v in env.items():
        out = out.replace("{" + k + "}", v)
    return out


def dig(obj, path: str):
    """ドット区切りパスでJSONを辿る。リストならlen()を返す。"""
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    if isinstance(cur, list):
        return len(cur)
    return cur


def run_check(check: dict, env: dict) -> dict:
    name = check["name"]
    req = check["request"]
    url = render(req["url"], env)
    headers = {k: render(v, env) for k, v in req.get("headers", {}).items()}

    # 未設定のプレースホルダが残っている場合はスキップ
    if "{" in url or any("{" in v for v in headers.values()):
        return {"name": name, "state": "skipped", "detail": "トークン未設定"}

    try:
        resp = requests.request(
            req.get("method", "GET"), url, headers=headers, timeout=20
        )
    except requests.RequestException as e:
        return {"name": name, "state": "alert", "detail": f"接続失敗: {e}"}

    expect = check.get("expect_status", 200)
    if resp.status_code != expect:
        return {
            "name": name,
            "state": "alert",
            "detail": f"HTTP {resp.status_code} (期待: {expect})",
        }

    count_path = check.get("count_path")
    if count_path:
        try:
            value = dig(resp.json(), count_path)
        except ValueError:
            return {"name": name, "state": "alert", "detail": "JSON解析失敗"}
        threshold = check.get("alert_if_count_gt", 0)
        if value is not None and value > threshold:
            return {
                "name": name,
                "state": "alert",
                "detail": f"{count_path}={value} (閾値: {threshold})",
            }

    return {"name": name, "state": "ok", "detail": ""}


def notify_slack(env: dict, alerts: list):
    url = env.get("SLACK_WEBHOOK_URL", "")
    if not url or not alerts:
        return
    lines = [f"• *{a['name']}*: {a['detail']}" for a in alerts]
    text = ":rotating_light: NW監視アラート\n" + "\n".join(lines)
    try:
        requests.post(url, json={"text": text}, timeout=10)
    except requests.RequestException as e:
        print(f"Slack通知失敗: {e}", flush=True)


def main():
    DATA_DIR.mkdir(exist_ok=True)
    prev_alert_names: set = set()

    while True:
        env = load_env()
        checks = yaml.safe_load(CHECKS_FILE.read_text()).get("checks", [])
        now = datetime.now(timezone.utc).isoformat()

        results = [run_check(c, env) for c in checks if c.get("enabled", True)]
        alerts = [r for r in results if r["state"] == "alert"]

        STATUS_FILE.write_text(
            json.dumps({"checked_at": now, "results": results}, ensure_ascii=False)
        )

        # 新規アラートのみ通知・記録（同一アラートの連続通知を抑止）
        new_alerts = [a for a in alerts if a["name"] not in prev_alert_names]
        if new_alerts:
            notify_slack(env, new_alerts)
            with ANOMALY_FILE.open("a") as f:
                for a in new_alerts:
                    f.write(json.dumps({"time": now, **a}, ensure_ascii=False) + "\n")
        prev_alert_names = {a["name"] for a in alerts}

        summary = ", ".join(f"{r['name']}:{r['state']}" for r in results) or "checksなし"
        print(f"[{now}] {summary}", flush=True)

        time.sleep(int(env.get("POLL_INTERVAL_SEC", "300")))


if __name__ == "__main__":
    main()
