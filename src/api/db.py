import sqlite3
import json
from typing import Optional, List, Dict
from datetime import datetime

CORE_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER,
    source TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    ingested_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(match_id, source)
);
"""

def init_deliveries_db(path: str) -> sqlite3.Connection:
    """
    Initialize (or open) the deliveries DB and ensure schema exists.
    Safe-migration behavior:
      - Creates table if missing.
      - Adds missing columns with ALTER TABLE if needed.
      - Creates indexes if possible.
    """
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    cur = conn.cursor()

    cur.execute(CORE_TABLE_DDL)

    cur.execute("PRAGMA table_info(deliveries);")
    existing_cols = {row[1] for row in cur.fetchall()}

    if "received_at" not in existing_cols:
        try:
            cur.execute("ALTER TABLE deliveries ADD COLUMN received_at TEXT;")
        except sqlite3.OperationalError:
            pass

    if "ingested_at" not in existing_cols:
        try:
            cur.execute("ALTER TABLE deliveries ADD COLUMN ingested_at TEXT DEFAULT CURRENT_TIMESTAMP;")
        except sqlite3.OperationalError:
            pass

    cur.execute("CREATE INDEX IF NOT EXISTS idx_deliveries_received_at ON deliveries(received_at);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_deliveries_ingested_at ON deliveries(ingested_at);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_deliveries_match_id ON deliveries(match_id);")

    return conn

def insert_delivery(conn: sqlite3.Connection,
                    match_id: Optional[int],
                    payload: dict,
                    source: Optional[str],
                    received_at: Optional[str] = None) -> bool:
    """
    Insert a delivery row. Returns True if persisted; False if duplicate (skipped).
    received_at: ISO timestamp string. If None, we set it to current UTC time.
    """
    cur = conn.cursor()
    payload_json = json.dumps(payload, ensure_ascii=False)
    if received_at is None:
        received_at = datetime.utcnow().isoformat() + "Z"
    try:
        cur.execute(
            "INSERT INTO deliveries (match_id, source, payload_json, received_at) VALUES (?, ?, ?, ?)",
            (match_id, source, payload_json, received_at)
        )
        return True
    except sqlite3.IntegrityError:
        return False

def exists_match_id(conn: sqlite3.Connection, match_id: int) -> bool:
    """
    Return True if any delivery exists with this match_id (regardless of source).
    Application-level idempotency check.
    """
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM deliveries WHERE match_id = ? LIMIT 1", (match_id,))
    return cur.fetchone() is not None

def query_deliveries(conn: sqlite3.Connection,
                     limit: int = 100,
                     offset: int = 0,
                     since: Optional[str] = None,
                     match_id: Optional[int] = None,
                     source: Optional[str] = None,
                     include_payload: bool = True) -> List[Dict]:
    """
    Return deliveries with pagination and optional filters.
    - include_payload: when False, payload_json isn't returned to reduce size
    """
    cur = conn.cursor()
    select_cols = "id, match_id, source, payload_json, received_at, ingested_at" if include_payload else "id, match_id, source, received_at, ingested_at"
    q = f"SELECT {select_cols} FROM deliveries"
    params = []
    clauses = []
    if since:
        clauses.append("received_at > ?")
        params.append(since)
    if match_id is not None:
        clauses.append("match_id = ?")
        params.append(match_id)
    if source:
        clauses.append("source = ?")
        params.append(source)
    if clauses:
        q += " WHERE " + " AND ".join(clauses)
    q += " ORDER BY received_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cur.execute(q, params)
    rows = []
    for r in cur.fetchall():
        if include_payload:
            id_, mid, src, payload_json, received_at, ingested_at = r
            try:
                payload = json.loads(payload_json)
            except Exception:
                payload = payload_json
            rows.append({
                "id": id_,
                "match_id": mid,
                "source": src,
                "payload": payload,
                "received_at": received_at,
                "ingested_at": ingested_at
            })
        else:
            id_, mid, src, received_at, ingested_at = r
            rows.append({
                "id": id_,
                "match_id": mid,
                "source": src,
                "received_at": received_at,
                "ingested_at": ingested_at
            })
    return rows

def simple_query_deliveries(conn: sqlite3.Connection, limit: int = 100, offset: int = 0) -> List[Dict]:
    """
    Very small, fast query used for lightweight listings: id, match_id, source, received_at.
    """
    cur = conn.cursor()
    q = "SELECT id, match_id, source, received_at FROM deliveries ORDER BY received_at DESC LIMIT ? OFFSET ?"
    cur.execute(q, (limit, offset))
    rows = []
    for r in cur.fetchall():
        id_, mid, src, received_at = r
        rows.append({
            "id": id_,
            "match_id": mid,
            "source": src,
            "received_at": received_at
        })
    return rows
