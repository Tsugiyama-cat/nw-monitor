# nw-monitor

Juniper Mist / HPE Aruba Networking Central のネットワーク監視スタック。
Dockerホスト（例: TS-LABホスト）上で動作し、以下を提供する。

- **チャットからの可視化**: Mac等のClaude Code/DesktopからMCP経由でNW状況を照会
- **定期監視**: LLMを使わないポーラーが閾値判定し、Slackへ通知（コストゼロ）
- **異常時の一次解析（任意）**: Codex CLI（ChatGPTプラン枠）で異常のみ解析

```
┌─ Mac (Claude Code / Pro) ──────────────────────────┐
│  可視化・深掘りは人が見るときだけ                      │
└──────┬──────────────────────────┬──────────────────┘
       │ MCP (HTTP)               │ MCP (HTTPS)
       ▼                          ▼
┌─ Dockerホスト ────────┐   Juniperホスト型 Mist MCP
│ central-mcp  :8811    │   https://mcp.ai.juniper.net/mcp/mist
│ webui        :8800    │   （ローカル常駐なし）
│ poller       (内部)   │──→ 異常時: Slack通知 + anomalies.jsonl
└───────────────────────┘        └→ scripts/analyze_latest.sh (codex exec)
```

## 前提

- Docker / Docker Compose v2
- （任意）Slack Incoming Webhook URL
- （任意）ホストに [Codex CLI](https://github.com/openai/codex)（`npm i -g @openai/codex` → `codex login`）

## セットアップ

```bash
git clone https://github.com/Tsugiyama-cat/nw-monitor.git
cd nw-monitor
cp config/runtime.env.example config/runtime.env   # 初回のみ（中身は空でOK）
docker compose up -d --build
```

ブラウザで `http://<ホストIP>:8800` を開き、トークン類を入力して保存する。

| 項目 | 取得方法 |
|---|---|
| Mist APIトークン | Mist管理画面 → Organization → API Tokens（Orgトークン推奨） |
| Mist Org ID | Mist管理画面のURL等から確認 |
| Central Access Token | New Central → API Gateway でトークン発行 |
| Slack Webhook URL | Slack App → Incoming Webhooks |

> **反映タイミング**: poller と webui は保存後すぐ反映。**central-mcp のみ
> `docker compose restart central-mcp` が必要**（起動時に環境変数を読むため）。

## Mac側 (Claude Code) のMCP登録

```bash
# Mist — Juniperホスト型なのでローカル常駐なし
claude mcp add --transport http mist https://mcp.ai.juniper.net/mcp/mist \
  --header "Authorization: Bearer <MIST_API_TOKEN>" \
  --header "X-Mist-Base-URL: https://api.mist.com"

# Aruba Central — このDockerホスト上のゲートウェイ経由
claude mcp add --transport http central http://<ホストIP>:8811/mcp
```

登録後、チャットで「全サイトのヘルス状態を表にして」等がそのまま動く。

## 定期監視のカスタマイズ

チェック内容は `checks.yml` で定義する（コード変更不要）。
URLやヘッダ内の `{KEY}` は GUI で保存した値に置換され、未設定のチェックは自動skipされる。

- `mist-alarms` のエンドポイント・閾値は環境に合わせて調整すること
- Central側のチェック（`central-auth`）はURL調整後に `enabled: true` にする
- 変更後は `docker compose restart poller`

同一アラートが続く間は再通知しない（復旧→再発で再通知）。

## Codexによる一次解析（任意）

異常があったときだけ `codex exec` で原因仮説をまとめ、Slackに送る。

```bash
# 手動実行
./scripts/analyze_latest.sh

# cronで15分ごとにチェック（新しい異常がなければ即終了し、Codex枠を消費しない）
crontab -e
*/15 * * * * cd /path/to/nw-monitor && ./scripts/analyze_latest.sh --notify
```

## 運用メモ

- 全コンテナ `restart: unless-stopped` — ホスト起動中のみ監視し、起動時に自動再開
- トークンは `config/runtime.env`（gitignore済み）にのみ保存される
- ポート8800/8811はラボセグメント内に閉じること（認証なしのため外部公開禁止）

## トラブルシュート

| 症状 | 確認 |
|---|---|
| GUIに「まだポーリング結果がありません」 | `docker compose logs poller` |
| mist-auth が alert (401) | トークンの有効期限・権限を確認 |
| MacからCentral MCPに繋がらない | `curl http://<ホストIP>:8811/mcp` で応答確認、FW確認 |
| central-mcp が起動しない | `docker compose logs central-mcp`（uvxの初回ダウンロードに時間がかかる場合あり） |
