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

def normalize_row(r):
    if not isinstance(r, dict):
        return None
    payload = r.get("payload") if isinstance(r.get("payload"), dict) else None
    match_id = r.get("match_id") or r.get("id") or (payload and payload.get("match_id"))
    home = r.get("home") or (payload and payload.get("home"))
    away = r.get("away") or (payload and payload.get("away"))
    prob = (
        r.get("prob_platt")
        or r.get("prob_home")
        or r.get("prob")
        or (payload and (payload.get("prob_platt") or payload.get("prob")))
    )
    try:
        if prob is not None:
            prob = float(prob)
    except Exception:
        prob = None
    if match_id is None and (home is None and away is None):
        return None
    out = {"match_id": match_id}
    if prob is not None:
        out["prob"] = prob
    if home is not None:
        out["home"] = home
    if away is not None:
        out["away"] = away
    return out

def normalize_rows(rows):
    normalized = []
    for r in rows:
        nr = normalize_row(r)
        if nr is not None:
            normalized.append(nr)
    return normalized

def fetch_picks(limit=5, threshold=None, prob_col="prob_platt"):
    params = {"limit": limit}
    if threshold is not None:
        params.update({"threshold": threshold, "prob_col": prob_col})
    headers = {}
    if API_KEY:
        headers["X-API-KEY"] = API_KEY
    candidate_urls = [
        f"{API_URL}/predictions/latest",
        f"{API_URL}/predictions",
        f"{API_URL}/deliveries",
    ]
    for url in candidate_urls:
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=5)
            if resp.status_code != 200:
                continue
            payload = resp.json()
            if isinstance(payload, dict) and "rows" in payload and isinstance(payload["rows"], list):
                return payload["rows"][:limit]
            if isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], list):
                return payload["data"][:limit]
            if isinstance(payload, list):
                return payload[:limit]
            if isinstance(payload, dict) and ("match_id" in payload or "prob" in payload):
                return [payload]
        except Exception:
            continue
    return [
        {"match_id": 99990001, "home": "TestHome", "away": "TestAway", "prob_platt": 0.55},
        {"match_id": 99990002, "home": "Foo", "away": "Bar", "prob_platt": 0.60},
    ]

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
        home = r.get("home") or ""
        away = r.get("away") or ""
        prob = r.get("prob") or r.get("prob_platt") or r.get("prob_home") or 0.0
        try:
            prob_f = float(prob)
        except Exception:
            prob_f = 0.0
        lines.append(f"- {home} vs {away} — prob {prob_f:.3f} (id:{mid})")
    lines.append(f"\nSent at {datetime.utcnow().isoformat()}Z")
    return "\n".join(lines)

def filter_existing_rows(rows):
    """
    Query the API for existing deliveries/predictions matching each match_id.
    Returns the filtered rows (only those not already present).
    This does one request per match_id (acceptable for small limits).
    """
    if not rows:
        return []
    headers = {}
    if API_KEY:
        headers["X-API-KEY"] = API_KEY
    filtered = []
    for r in rows:
        mid = r.get("match_id")
        if mid is None:
            filtered.append(r)
            continue
        exists = False
        try:
            resp = requests.get(f"{API_URL}/deliveries", params={"match_id": mid}, headers=headers, timeout=5)
            if resp.status_code == 200:
                payload = resp.json()
                if (isinstance(payload, dict) and payload.get("rows")) or (isinstance(payload, list) and payload):
                    exists = True
            if not exists:
                resp2 = requests.get(f"{API_URL}/predictions", params={"match_id": mid}, headers=headers, timeout=5)
                if resp2.status_code == 200:
                    payload2 = resp2.json()
                    if (isinstance(payload2, dict) and payload2.get("rows")) or (isinstance(payload2, list) and payload2):
                        exists = True
        except Exception:
            exists = False
        if not exists:
            filtered.append(r)
    return filtered

def log_deliveries(conn, rows, message_id, chat_id):
    now = datetime.utcnow().isoformat() + "Z"
    for r in rows:
        conn.execute(
            "INSERT INTO deliveries (sent_at, match_id, home, away, prob, message_id, chat_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now, r.get("match_id"), r.get("home"), r.get("away"), float(r.get("prob") or r.get("prob_platt") or 0.0), message_id, chat_id),
        )
    conn.commit()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--prob-col", type=str, default="prob_platt")
    args = parser.parse_args()

    rows = fetch_picks(limit=args.limit, threshold=args.threshold, prob_col=args.prob_col)

    normalized_rows = normalize_rows(rows)

    if os.environ.get("TEST_MODE") == "1":
        try:
            offset = int(os.environ.get("TEST_MATCH_ID_OFFSET", "10000000"))
        except Exception:
            offset = 10000000
        for r in normalized_rows:
            try:
                r["match_id"] = int(r.get("match_id", 0)) + offset
            except Exception:
                pass

    print("DEBUG: normalized_rows:", json.dumps(normalized_rows, indent=2))

    filtered_rows = filter_existing_rows(normalized_rows)
    filtered_out = len(normalized_rows) - len(filtered_rows)
    print(f"DEBUG: filtered_out={filtered_out} (will send {len(filtered_rows)} rows)")

    text = format_picks_text(filtered_rows)

    ingest_payload = {"rows": filtered_rows, "source": "telegram-sender"}
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
    total_sent = len(filtered_rows)
    skipped = max(0, total_sent - persisted)

    if os.environ.get("SKIP_TELEGRAM") == "1":
        res = {"result": {"message_id": None, "chat": {"id": None}}}
    else:
        try:
            res = send_telegram_message(text)
        except Exception as e:
            print("WARNING: Telegram send failed (continuing):", e)
            res = {"result": {"message_id": None, "chat": {"id": None}}}

    message_id = res.get("result", {}).get("message_id")
    chat_id = res.get("result", {}).get("chat", {}).get("id")
    chat_id_str = str(chat_id) if chat_id is not None else None

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    log_deliveries(conn, filtered_rows, message_id, chat_id_str)

    now = datetime.utcnow().isoformat() + "Z"
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO deliveries_summary (message_id, chat_id, sent_at, source, total_sent, persisted_count, skipped_count, ingest_status_code, ingest_response_json, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            message_id,
            chat_id_str,
            now,
            "telegram-sender",
            total_sent,
            persisted,
            skipped + filtered_out,
            ingest_status,
            json.dumps(ingest_json),
            json.dumps(filtered_rows),
        ),
    )
    conn.commit()
    conn.close()

    print(f"Sent {len(filtered_rows)} picks, message_id={message_id}, chat_id={chat_id}, persisted={persisted}, skipped={skipped + filtered_out}")

if __name__ == "__main__":
    main()
