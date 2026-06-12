#!/usr/bin/env bash
# 直近の異常を Codex CLI (ChatGPTプラン枠) で一次解析する。
# Dockerホスト上で実行する想定（codexはホスト側にインストール・ログイン済みであること）。
#
# 使い方:
#   ./scripts/analyze_latest.sh          # 直近5件を解析して標準出力へ
#
# cronで「異常があったときだけ」回す例 (15分ごと):
#   */15 * * * * cd /path/to/nw-monitor && ./scripts/analyze_latest.sh --notify
set -euo pipefail
cd "$(dirname "$0")/.."

ANOMALY_FILE="data/anomalies.jsonl"
MARKER_FILE="data/.last_analyzed"

[ -s "$ANOMALY_FILE" ] || { echo "異常記録なし"; exit 0; }

# 前回解析以降に新しい異常がなければ何もしない（Codex枠を消費しない）
if [ -f "$MARKER_FILE" ] && [ ! "$ANOMALY_FILE" -nt "$MARKER_FILE" ]; then
  exit 0
fi

RECENT=$(tail -5 "$ANOMALY_FILE")
STATUS=$(cat data/status.json 2>/dev/null || echo "{}")

RESULT=$(codex exec "あなたはネットワーク監視の一次解析担当です。
以下はJuniper Mist / Aruba Central環境の監視で検出された異常です。
考えられる原因の仮説と、確認すべきコマンド・画面を簡潔に日本語でまとめてください。

## 直近の異常
${RECENT}

## 現在の全チェック状態
${STATUS}")

echo "$RESULT"
touch "$MARKER_FILE"

# --notify 指定時はSlackにも送る
if [ "${1:-}" = "--notify" ]; then
  WEBHOOK=$(grep '^SLACK_WEBHOOK_URL=' config/runtime.env 2>/dev/null | cut -d= -f2-)
  if [ -n "$WEBHOOK" ]; then
    PAYLOAD=$(printf '%s' "$RESULT" | python3 -c 'import json,sys; print(json.dumps({"text": ":mag: Codex一次解析\n" + sys.stdin.read()}))')
    curl -s -X POST -H 'Content-Type: application/json' -d "$PAYLOAD" "$WEBHOOK" > /dev/null
  fi
fi
