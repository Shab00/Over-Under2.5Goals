#!/usr/bin/env python3
import sqlite3, json, sys

DB = sys.argv[1] if len(sys.argv) > 1 else "deliveries.db"

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, message_id, chat_id, sent_at, total_sent, persisted_count, skipped_count, ingest_status_code, ingest_response_json FROM deliveries_summary ORDER BY id DESC LIMIT 1")
row = cur.fetchone()
if not row:
    print("No summary rows found.")
else:
    id, message_id, chat_id, sent_at, total_sent, persisted_count, skipped_count, status, ingest_json = row
    print(f"id={id} message_id={message_id} chat_id={chat_id} sent_at={sent_at}")
    print(f"total_sent={total_sent} persisted={persisted_count} skipped={skipped_count} ingest_status={status}")
    try:
        print("ingest_response:", json.dumps(json.loads(ingest_json), indent=2))
    except Exception:
        print("ingest_response_json:", ingest_json)
conn.close()
