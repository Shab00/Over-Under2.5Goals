import os
import sqlite3
import requests
import argparse
from datetime import datetime

API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000")
API_KEY = os.environ.get("API_KEY")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

DB_PATH = os.environ.get("DELIVERIES_DB", "deliveries.db")

def init_db(conn):
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

    res = send_telegram_message(text)
    message_id = res.get("result", {}).get("message_id")
    chat_id = str(res.get("result", {}).get("chat", {}).get("id"))

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    log_deliveries(conn, rows, message_id, chat_id)
    conn.close()

    print(f"Sent {len(rows)} picks, message_id={message_id}, chat_id={chat_id}")

if __name__ == "__main__":
    main()
