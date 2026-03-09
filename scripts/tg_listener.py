#!/usr/bin/env python3
"""
Telegram command listener for x-feed-monitor.

Send commands to @feed_parasite_bot to control the monitor:
  /run   — trigger a fresh fetch right now
  /clear — clear the seen list (useful for testing)
  /status — show last run info

Keep this running in the background. Add to Task Scheduler at startup
or just run it in a terminal: python scripts/tg_listener.py
"""

import json
import subprocess
import sys
import time
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
LOG_FILE = DATA / "x-monitor-log.jsonl"
SEEN_FILE = DATA / "x-feed-seen.json"

TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"      # from @BotFather
AUTHORIZED_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"   # your personal chat ID
API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

PYTHON = sys.executable
MONITOR_SCRIPT = str(ROOT / "scripts" / "x_feed_monitor.py")


def send(text: str):
    try:
        httpx.post(
            f"{API}/sendMessage",
            json={
                "chat_id": AUTHORIZED_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
    except Exception as e:
        print(f"send error: {e}")


def get_updates(offset: int | None) -> list:
    try:
        r = httpx.get(
            f"{API}/getUpdates",
            params={"timeout": 30, "allowed_updates": ["message"], **({"offset": offset} if offset else {})},
            timeout=35,
        )
        return r.json().get("result", [])
    except Exception as e:
        print(f"poll error: {e}")
        return []


def run_monitor():
    """Run x_feed_monitor.py as a subprocess, stripped of CLAUDECODE env var."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    result = subprocess.run(
        [PYTHON, MONITOR_SCRIPT],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return result.returncode, result.stdout, result.stderr


def last_run_status() -> str:
    if not LOG_FILE.exists():
        return "No runs logged yet."
    lines = LOG_FILE.read_text().strip().splitlines()
    if not lines:
        return "No runs logged yet."
    last = json.loads(lines[-1])
    ts = last.get("ts", "?")
    status = last.get("status", "?")
    count = last.get("count", 0)
    suggestions = last.get("suggestions", 0)
    return f"Last run: {ts[:16].replace('T', ' ')} UTC\nStatus: {status}\nTweets: {count} | Suggestions: {suggestions}"


def handle_command(text: str):
    cmd = text.strip().lower().split()[0]

    if cmd == "/run":
        send("Fetching feed... ⏳")
        try:
            code, out, err = run_monitor()
            if code == 0:
                send("Done. Check above for new tweets. ✓")
            else:
                send(f"Script exited with error:\n<code>{err[:500]}</code>")
        except subprocess.TimeoutExpired:
            send("Timed out after 3 minutes.")
        except Exception as e:
            send(f"Failed to run: {e}")

    elif cmd == "/clear":
        SEEN_FILE.write_text('{"ids": []}')
        send("Seen list cleared. Next /run will fetch recent tweets fresh.")

    elif cmd == "/status":
        send(last_run_status())

    else:
        send(
            "Commands:\n"
            "/run — fetch feed now\n"
            "/clear — reset seen list\n"
            "/status — last run info"
        )


def main():
    print(f"[{datetime.now()}] Listener started. Waiting for commands in @feed_parasite_bot...")
    offset = None
    while True:
        updates = get_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message", {})
            chat_id = str(msg.get("chat", {}).get("id", ""))
            text = msg.get("text", "").strip()

            if not text or not text.startswith("/"):
                continue
            if chat_id != AUTHORIZED_CHAT_ID:
                print(f"Ignored message from unauthorized chat {chat_id}")
                continue

            print(f"[{datetime.now()}] Command: {text}")
            handle_command(text)

        if not updates:
            time.sleep(1)


if __name__ == "__main__":
    main()
