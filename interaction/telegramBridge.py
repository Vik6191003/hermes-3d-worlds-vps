#!/usr/bin/env python3
"""
Phase 5 — Clarification Bridge: Telegram Bot for 3D Game World Builder
Receives "need clarification" signals from the pipeline and asks Alexander via Telegram.
Stores answers so the pipeline can regenerate the world with corrections.
"""
import os
import sys
import json
import asyncio
import signal
import logging
from datetime import datetime, timezone
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
import threading

# Add project root to path
BASE = "/root/hermes-3d-worlds"
sys.path.insert(0, BASE)

# ── Config ─────────────────────────────────────────────────────────────────

CONFIG_PATH = f"{BASE}/config.json"
DATA_DIR = f"{BASE}/data"
CLARIFY_FILE = f"{DATA_DIR}/clarification.json"
LOG_FILE = f"{DATA_DIR}/logs/clarification_bridge.log"

os.makedirs(f"{DATA_DIR}/logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("clarify")

# ── State ───────────────────────────────────────────────────────────────────

def load_config():
    if not os.path.exists(CONFIG_PATH):
        log.warning("config.json not found — using defaults")
        return {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}
    with open(CONFIG_PATH) as f:
        raw = json.load(f)
    # Normalize key names (some fields have wrong names in config)
    return {
        "TELEGRAM_BOT_TOKEN": raw.get("TELEGRAM_BOT_TOKEN") or raw.get("MICROSOFT_CLIENT_ID", ""),
        "TELEGRAM_CHAT_ID": raw.get("TELEGRAM_CHAT_ID") or raw.get("TELEGRAM_CHAT_ID", ""),
    }

def load_clarifications():
    if not os.path.exists(CLARIFY_FILE):
        return {}
    try:
        with open(CLARIFY_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_clarifications(data):
    with open(CLARIFY_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ── Telegram Client ─────────────────────────────────────────────────────────

TELEGRAM_API = "https://api.telegram.org"

def send_telegram_message(token: str, chat_id: str, text: str):
    import urllib.request
    import urllib.parse

    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": json.dumps({
            "force_reply": True,
            "input_field_placeholder": "Your answer here...",
        }),
    }).encode()

    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        log.error(f"Telegram send failed: {e}")
        return None

def send_telegram_reply(token: str, chat_id: str, text: str, reply_to_message_id: str = None):
    import urllib.request
    import urllib.parse

    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    params = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    if reply_to_message_id:
        params["reply_to_message_id"] = reply_to_message_id

    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        log.error(f"Telegram reply failed: {e}")
        return None

class TelegramPoller:
    """Long-polling Telegram bot — no SSL cert needed."""

    def __init__(self, token: str, chat_id: str, on_answer: callable):
        self.token = token
        self.chat_id = chat_id
        self.on_answer = on_answer
        self.offset = 0
        self.running = False

    def start(self):
        self.running = True
        self.thread = Thread(target=self._poll_loop, daemon=True)
        self.thread.start()
        log.info("Telegram poller started")

    def stop(self):
        self.running = False

    def _poll_loop(self):
        while self.running:
            try:
                updates = self._get_updates()
                for update in updates:
                    self._handle_update(update)
                    self.offset = update["update_id"] + 1
            except Exception as e:
                log.error(f"Poll error: {e}")
                import time
                time.sleep(5)

    def _get_updates(self):
        import urllib.request
        import urllib.parse

        url = f"{TELEGRAM_API}/bot{self.token}/getUpdates"
        params = {"offset": self.offset, "timeout": 30}
        data = urllib.parse.urlencode(params).encode()

        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=35) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                return result.get("result", [])
            return []

    def _handle_update(self, update):
        msg = update.get("message", {})
        text = msg.get("text", "").strip()
        if not text:
            return
        chat_id_str = str(msg.get("chat", {}).get("id", ""))
        if chat_id_str != self.chat_id:
            return  # Ignore other chats

        msg_id = msg.get("message_id")
        log.info(f"Received answer from {self.chat_id}: {text}")

        # Extract world_id from message if it references a pending question
        # Format expected: "world_id:answer" or plain answer (matched against most recent)
        clarifications = load_clarifications()
        if clarifications:
            latest_key = max(clarifications.keys())
            clarifications[latest_key]["answers"] = clarifications[latest_key].get("answers", [])
            clarifications[latest_key]["answers"].append(text)
            clarifications[latest_key]["answered_at"] = datetime.now(timezone.utc).isoformat()
            save_clarifications(clarifications)
            log.info(f"Stored answer for world_id={latest_key}")

        # Confirm receipt
        send_telegram_reply(
            self.token, self.chat_id,
            f"✅ Got it! World will regenerate with your answer: \"{text}\"",
            str(msg_id),
        )
        if self.on_answer:
            self.on_answer(latest_key, text)

# ── HTTP Server ─────────────────────────────────────────────────────────────

class ClarifyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        log.info(format % args)

    def do_POST(self):
        if self.path == "/ask":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON")
                return

            questions = data.get("questions", [])
            world_id = data.get("world_id", "unknown")
            if not questions:
                self.send_error(400, "No questions provided")
                return

            # Store pending clarification
            clarifications = load_clarifications()
            clarifications[world_id] = {
                "questions": questions,
                "answers": [],
                "asked_at": datetime.now(timezone.utc).isoformat(),
                "status": "pending",
            }
            save_clarifications(clarifications)

            # Send to Telegram — one message per question (max 5)
            token = config["TELEGRAM_BOT_TOKEN"]
            chat_id = config["TELEGRAM_CHAT_ID"]
            header = f"🎮 <b>3D World Clarification</b>\nWorld: <code>{world_id}</code>\n\n"
            for i, q in enumerate(questions[:5]):
                full_msg = header + f"Q{i+1}: {q}" if i == 0 else f"Q{i+1}: {q}"
                result = send_telegram_message(token, chat_id, full_msg)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = json.dumps({"status": "ok", "world_id": world_id, "questions_asked": len(questions)})
            self.wfile.write(resp.encode())

        elif self.path == "/status":
            clarifications = load_clarifications()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(clarifications).encode())

        else:
            self.send_error(404)

    def do_GET(self):
        if self.path.startswith("/status/"):
            world_id = self.path.split("/status/")[1]
            clarifications = load_clarifications()
            data = clarifications.get(world_id, {})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}).encode())
        else:
            self.send_error(404)

# ── Push Updates (Hermes calls this to notify Alexander) ────────────────────

def push_update(token: str, chat_id: str, text: str):
    """Send an update to Telegram from Hermes at any time."""
    return send_telegram_message(token, chat_id, text)

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    global config
    config = load_config()

    if not config["TELEGRAM_BOT_TOKEN"]:
        log.error("TELEGRAM_BOT_TOKEN not set in config.json — exiting")
        sys.exit(1)
    if not config["TELEGRAM_CHAT_ID"]:
        log.error("TELEGRAM_CHAT_ID not set in config.json — exiting")
        sys.exit(1)

    log.info("Starting Hermes 3D Clarification Bridge...")

    # Start Telegram poller
    def on_answer(world_id, answer):
        log.info(f"Answer received: world={world_id} answer={answer}")

    poller = TelegramPoller(
        config["TELEGRAM_BOT_TOKEN"],
        config["TELEGRAM_CHAT_ID"],
        on_answer,
    )
    poller.start()

    # Start HTTP server on port 18792
    server_address = ("127.0.0.1", 18792)
    httpd = HTTPServer(server_address, ClarifyHandler)
    log.info(f"HTTP server listening on http://127.0.0.1:18792")

    # Graceful shutdown
    def shutdown_handler(signum, frame):
        log.info("Shutting down...")
        poller.stop()
        httpd.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    # Also send a startup message
    send_telegram_message(
        config["TELEGRAM_BOT_TOKEN"],
        config["TELEGRAM_CHAT_ID"],
        "🏝️ Hermes 3D Worlds Clarification Bridge is live.\nI'll ask you questions here when the AI needs help identifying a game screenshot.",
    )

    httpd.serve_forever()

if __name__ == "__main__":
    main()
