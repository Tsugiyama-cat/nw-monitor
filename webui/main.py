"""トークン入力・監視状態確認用のWeb GUI.

POST /api/config で config/runtime.env を書き換える。
シークレット系は値の末尾4文字のみGUIに返す（値そのものは返さない）。
"""
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

CONFIG_ENV = Path("/config/runtime.env")
STATUS_FILE = Path("/data/status.json")
ANOMALY_FILE = Path("/data/anomalies.jsonl")

FIELDS = [
    # (キー, ラベル, シークレットか)
    ("MIST_BASE_URL", "Mist Base URL (例: https://api.mist.com)", False),
    ("MIST_API_TOKEN", "Mist APIトークン", True),
    ("MIST_ORG_ID", "Mist Org ID", False),
    ("CENTRAL_BASE_URL", "Central Base URL", False),
    ("CENTRAL_CLIENT_ID", "Central Client ID", False),
    ("CENTRAL_CLIENT_SECRET", "Central Client Secret", True),
    ("CENTRAL_ACCESS_TOKEN", "Central Access Token", True),
    ("SLACK_BOT_TOKEN", "Slack Botトークン (xoxb-...)", True),
    ("SLACK_CHANNEL_ID", "Slack チャンネルID (例: C0123456789)", False),
    ("POLL_INTERVAL_SEC", "ポーリング間隔(秒)", False),
]
SECRET_KEYS = {k for k, _, secret in FIELDS if secret}

app = FastAPI(title="nw-monitor")


def load_env() -> dict:
    env = {}
    if CONFIG_ENV.exists():
        for line in CONFIG_ENV.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def save_env(env: dict):
    lines = [f"{k}={v}" for k, v in env.items() if v]
    CONFIG_ENV.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_ENV.write_text("\n".join(lines) + "\n")


class ConfigUpdate(BaseModel):
    values: dict[str, str]


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/api/fields")
def fields():
    return [{"key": k, "label": label, "secret": secret} for k, label, secret in FIELDS]


@app.get("/api/config")
def get_config():
    env = load_env()
    masked = {}
    for k, v in env.items():
        if k in SECRET_KEYS and v:
            masked[k] = f"****{v[-4:]}" if len(v) > 4 else "****"
        else:
            masked[k] = v
    return masked


@app.post("/api/config")
def set_config(update: ConfigUpdate):
    env = load_env()
    for k, v in update.values.items():
        v = v.strip()
        if not v or v.startswith("****"):
            continue  # 空欄・マスク表示のままの項目は既存値を維持
        env[k] = v
    save_env(env)
    return {"saved": True, "note": "central-mcpコンテナは再起動するまで旧トークンを使います"}


@app.get("/api/status")
def status():
    result = {"status": None, "anomalies": []}
    if STATUS_FILE.exists():
        result["status"] = json.loads(STATUS_FILE.read_text())
    if ANOMALY_FILE.exists():
        lines = ANOMALY_FILE.read_text().splitlines()
        result["anomalies"] = [json.loads(l) for l in lines[-20:]][::-1]
    return JSONResponse(result)
