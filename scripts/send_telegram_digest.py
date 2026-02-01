import os
import sqlite3
import requests
import argparse
import json
from datetime import datetime

API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000")
API_KEY = os.environ.get("API_KEY")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

DB_PATH = os.environ.get("DELIVERIES_DB", "deliveries.db")

def init_db(conn):
    # per-pick deliveries table (existing)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sent_at TEXT NOT NULL,
            match_id INTEGER,
            home TEXT,
            away TEXT,
            prob REAL,
            message_id INTEGER,
            chat_id TEXT
        )
        """
    )
    # summary table: one row per Telegram send / ETL run
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS deliveries_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            chat_id TEXT,
            sent_at TEXT NOT NULL,
            source TEXT,
            total_sent INTEGER DEFAULT 0,
            persisted_count INTEGER DEFAULT 0,
            skipped_count INTEGER DEFAULT 0,
            ingest_status_code INTEGER,
            ingest_response_json TEXT,
            payload_json TEXT
        )
        """
    )
    conn.commit()

def fetch_picks(limit=5, threshold=None, prob_col="prob_platt"):
    params = {"limit": limit}
    if threshold is not None:
        params.update({"threshold": threshold, "prob_col": prob_col})
    headers = {}
    if API_KEY:
        headers["X-API-KEY"] = API_KEY
    resp = requests.get(f"{API_URL}/predictions/latest", params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json().get("rows", [])

def send_telegram_message(text):
    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in environment.")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    r = requests.post(url, json=payload, timeout=10)
    r.raise_for_status()
    return r.json()

def format_picks_text(rows):
    if not rows:
        return "No picks found."
    lines = ["Top picks:"]
    for r in rows:
        mid = r.get("match_id")
        home = r.get("home")
        away = r.get("away")
        prob = r.get("prob_platt") or r.get("prob_home") or r.get("prob")
        lines.append(f"- {home} vs {away} — prob {prob:.3f} (id:{mid})")
    lines.append(f"\nSent at {datetime.utcnow().isoformat()}Z")
    return "\n".join(lines)

def log_deliveries(conn, rows, message_id, chat_id):
    now = datetime.utcnow().isoformat() + "Z"
    for r in rows:
        conn.execute(
            "INSERT INTO deliveries (sent_at, match_id, home, away, prob, message_id, chat_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now, r.get("match_id"), r.get("home"), r.get("away"), float(r.get("prob_platt") or r.get("prob_home") or 0.0), message_id, chat_id),
        )
    conn.commit()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--prob-col", type=str, default="prob_platt")
    args = parser.parse_args()

    rows = fetch_picks(limit=args.limit, threshold=args.threshold, prob_col=args.prob_col)
    text = format_picks_text(rows)

    # POST rows to /ingest to get persisted counts
    ingest_payload = {"rows": rows, "source": "telegram-sender"}
    ingest_headers = {"Content-Type": "application/json"}
    if API_KEY:
        ingest_headers["X-API-KEY"] = API_KEY

    try:
        ingest_resp = requests.post(f"{API_URL}/ingest", json=ingest_payload, headers=ingest_headers, timeout=10)
        ingest_status = ingest_resp.status_code
        try:
            ingest_json = ingest_resp.json()
        except Exception:
            ingest_json = {"error": "invalid-json"}
    except Exception as e:
        ingest_status = None
        ingest_json = {"error": f"ingest-failed: {str(e)}"}

    persisted = int(ingest_json.get("persisted", 0))
    total_sent = len(rows)
    skipped = max(0, total_sent - persisted)

    # Send Telegram message
    res = send_telegram_message(text)
    message_id = res.get("result", {}).get("message_id")
    chat_id = str(res.get("result", {}).get("chat", {}).get("id"))

    # Log per-pick deliveries (existing behaviour)
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    log_deliveries(conn, rows, message_id, chat_id)

    # Log summary row with persisted/skipped and ingest response
    now = datetime.utcnow().isoformat() + "Z"
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO deliveries_summary (message_id, chat_id, sent_at, source, total_sent, persisted_count, skipped_count, ingest_status_code, ingest_response_json, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            message_id,
            chat_id,
            now,
            "telegram-sender",
            total_sent,
            persisted,
            skipped,
            ingest_status,
            json.dumps(ingest_json),
            json.dumps(rows),
        ),
    )
    conn.commit()
    conn.close()

    print(f"Sent {len(rows)} picks, message_id={message_id}, chat_id={chat_id}, persisted={persisted}, skipped={skipped}")

if __name__ == "__main__":
    main()
