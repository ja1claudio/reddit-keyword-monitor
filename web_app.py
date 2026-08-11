from __future__ import annotations

import json
import os
import queue
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from monitor import append_csv, build_reddit_client, collect_once, load_config, read_seen, write_seen


APP_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
if getattr(__import__("sys"), "frozen", False):
    APP_DIR = Path(__import__("sys").executable).resolve().parent
CONFIG_PATH = APP_DIR / "user_config.json"
ENV_PATH = APP_DIR / ".env"

STATE = {"running": False, "status": "Ready", "logs": []}
STOP = threading.Event()
LOCK = threading.Lock()

HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reddit Keyword Monitor</title><style>
body{font-family:system-ui,sans-serif;background:#f5f6f8;color:#17202a;margin:0}.wrap{max-width:900px;margin:32px auto;padding:0 18px}h1{margin-bottom:4px}.card{background:white;border:1px solid #dde1e7;border-radius:12px;padding:18px;margin:14px 0;box-shadow:0 3px 14px #0000000b}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}label{display:block;font-weight:650;margin:9px 0 5px}textarea,input{box-sizing:border-box;width:100%;border:1px solid #bbc2cc;border-radius:7px;padding:9px;font:inherit}textarea{height:130px;resize:vertical}.row{display:flex;gap:10px;align-items:center}.row>div{flex:1}button{border:0;border-radius:8px;padding:11px 16px;font-weight:700;cursor:pointer;background:#ff4500;color:white}button.secondary{background:#59636e}button:disabled{opacity:.5}pre{background:#101419;color:#d8e2ec;padding:13px;border-radius:8px;height:170px;overflow:auto;white-space:pre-wrap}.pill{float:right;background:#e9eef5;padding:6px 10px;border-radius:99px;font-weight:650}@media(max-width:650px){.grid{grid-template-columns:1fr}}
</style></head><body><main class="wrap"><span class="pill" id="status">Ready</span><h1>Reddit Keyword Monitor</h1><p>Automatically save relevant new conversations to CSV.</p>
<section class="card"><div class="grid"><div><label>Subreddits — one per line</label><textarea id="subreddits">marketing
smallbusiness</textarea></div><div><label>Keywords or phrases — one per line</label><textarea id="keywords">not converting
struggling
confused</textarea></div></div>
<div class="row"><div><label>Scan every (minutes)</label><input id="interval" type="number" min="1" value="15"></div><div><label>Posts per subreddit</label><input id="limit" type="number" min="1" max="100" value="50"></div></div>
<label>CSV output path</label><input id="csv_path" value="output/reddit_matches.csv"></section>
<section class="card"><h2>Reddit API credentials</h2><label>Client ID</label><input id="client_id"><label>Client secret</label><input id="client_secret" type="password"><label>User agent</label><input id="user_agent" value="desktop:keyword-monitor:1.0 (by your_username)"></section>
<div class="row"><button id="start" onclick="action('start')">Start monitoring</button><button onclick="action('once')">Run one scan</button><button class="secondary" onclick="action('stop')">Stop</button></div>
<section class="card"><h2>Activity</h2><pre id="logs">Ready.</pre></section></main><script>
const lines=id=>document.getElementById(id).value.split('\n').map(x=>x.trim()).filter(Boolean);
const payload=()=>({subreddits:lines('subreddits'),keywords:lines('keywords'),interval_minutes:+interval.value,limit_per_subreddit:+limit.value,csv_path:csv_path.value,client_id:client_id.value,client_secret:client_secret.value,user_agent:user_agent.value});
async function action(name){let options={method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload())};let r=await fetch('/api/'+name,options);let j=await r.json();if(!r.ok)alert(j.error||'Request failed');refresh()}
async function refresh(){let j=await(await fetch('/api/status')).json();status.textContent=j.status;logs.textContent=(j.logs||[]).join('\n')||'Ready.';start.disabled=j.running;logs.scrollTop=logs.scrollHeight}
setInterval(refresh,1500);refresh();</script></body></html>"""


def add_log(message: str) -> None:
    with LOCK:
        STATE["logs"] = (STATE["logs"] + [message])[-200:]


def save_settings(data: dict) -> dict:
    minutes = int(data.get("interval_minutes", 15))
    if minutes < 1:
        raise ValueError("The interval must be at least one minute")
    config = {
        "subreddits": data.get("subreddits", []),
        "keywords": data.get("keywords", []),
        "limit_per_subreddit": int(data.get("limit_per_subreddit", 50)),
        "output": "csv",
        "csv_path": str((APP_DIR / data.get("csv_path", "output/reddit_matches.csv")).resolve()) if not Path(data.get("csv_path", "")).is_absolute() else data["csv_path"],
        "state_path": str(APP_DIR / "data" / "state.json"),
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    config = load_config(CONFIG_PATH)
    credentials = {key: str(data.get(key, "")).strip() for key in ("client_id", "client_secret", "user_agent")}
    if not all(credentials.values()):
        raise ValueError("Enter the client ID, client secret, and user agent")
    if any("\n" in value or "\r" in value for value in credentials.values()):
        raise ValueError("Credential fields cannot contain line breaks")
    ENV_PATH.write_text(
        f"REDDIT_CLIENT_ID={credentials['client_id']}\nREDDIT_CLIENT_SECRET={credentials['client_secret']}\nREDDIT_USER_AGENT={credentials['user_agent']}\n",
        encoding="utf-8",
    )
    os.environ.update(REDDIT_CLIENT_ID=credentials["client_id"], REDDIT_CLIENT_SECRET=credentials["client_secret"], REDDIT_USER_AGENT=credentials["user_agent"])
    config["interval_minutes"] = minutes
    return config


def worker(config: dict, once: bool) -> None:
    try:
        reddit = build_reddit_client()
        state_path = Path(config["state_path"])
        seen = read_seen(state_path)
        while not STOP.is_set():
            add_log("Scanning " + ", ".join("r/" + name for name in config["subreddits"]) + "...")
            matches = collect_once(reddit, config, seen)
            append_csv(Path(config["csv_path"]), matches)
            write_seen(state_path, seen)
            add_log(f"Scan complete: {len(matches)} new match(es).")
            if once or STOP.wait(config["interval_minutes"] * 60):
                break
    except Exception as exc:
        add_log("ERROR: " + str(exc))
    finally:
        with LOCK:
            STATE.update(running=False, status="Ready")


class Handler(BaseHTTPRequestHandler):
    def _json(self, value: dict, status: int = 200) -> None:
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/api/status":
            with LOCK:
                self._json(dict(STATE))
            return
        body = HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size > 100_000:
                self._json({"error": "Request is too large"}, 413)
                return
            data = json.loads(self.rfile.read(size) or b"{}")
            action = urlparse(self.path).path.rsplit("/", 1)[-1]
            if action == "stop":
                STOP.set()
                with LOCK: STATE["status"] = "Stopping..."
                self._json({"ok": True})
                return
            if action not in {"start", "once"}:
                self._json({"error": "Unknown action"}, 404)
                return
            with LOCK:
                if STATE["running"]:
                    self._json({"error": "The monitor is already running"}, 409)
                    return
            config = save_settings(data)
            STOP.clear()
            with LOCK: STATE.update(running=True, status="Monitoring")
            threading.Thread(target=worker, args=(config, action == "once"), daemon=True).start()
            self._json({"ok": True})
        except Exception as exc:
            self._json({"error": str(exc)}, 400)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    threading.Timer(0.6, lambda: webbrowser.open("http://127.0.0.1:8765")).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
