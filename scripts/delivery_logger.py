import sqlite3
import json
import time
from typing import Any, Dict, List

def log_delivery(
    db_path: str,
    source: str,
    rows: List[Dict[str, Any]],
    persisted_count: int,
    skipped_count: int,
    metadata: Dict[str, Any] = None,
) -> None:
    """
    Insert a delivery record into deliveries table recording persisted/skipped counts.
    Adjust column names to match your schema if necessary.
    """
    metadata = metadata or {}
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    payload_json = json.dumps({
        "rows": rows,
        "meta": metadata,
    }, default=str)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # If your deliveries table has different columns, adjust this INSERT to match.
    cur.execute("""
    INSERT INTO deliveries
      (source, payload_json, ingested_at, received_at, persisted_count, skipped_count)
    VALUES (?,?,?,?,?,?)
    """, (
        source,
        payload_json,
        now,
        now,
        int(persisted_count),
        int(skipped_count),
    ))
    conn.commit()
    conn.close()
