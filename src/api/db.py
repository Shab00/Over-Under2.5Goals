import sqlite3
import json
from typing import Optional, List, Dict

DDL = """
CREATE TABLE IF NOT EXISTS deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER,
    source TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    ingested_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(match_id, source)
);

CREATE INDEX IF NOT EXISTS idx_deliveries_ingested_at ON deliveries(ingested_at);
CREATE INDEX IF NOT EXISTS idx_deliveries_match_id ON deliveries(match_id);
"""

def init_deliveries_db(path: str) -> sqlite3.Connection:
    """
    Initialize (or open) the deliveries DB and ensure schema exists.
    Returns an sqlite3.Connection (check_same_thread=False to allow reuse across threads).
    """
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    cur = conn.cursor()
    cur.executescript(DDL)
    return conn

def insert_delivery(conn: sqlite3.Connection, match_id: Optional[int], payload: dict, source: Optional[str]) -> bool:
    """
    Insert a delivery row. Returns True if persisted; False if duplicate (skipped).
    """
    cur = conn.cursor()
    payload_json = json.dumps(payload, ensure_ascii=False)
    try:
        cur.execute(
            "INSERT INTO deliveries (match_id, source, payload_json) VALUES (?, ?, ?)",
            (match_id, source, payload_json)
        )
        return True
    except sqlite3.IntegrityError:
        # duplicate (match_id, source) => skip
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
    - offset: pagination offset
    - include_payload: when False, payload_json isn't returned to reduce size
    """
    cur = conn.cursor()
    select_cols = "id, match_id, source, payload_json, ingested_at" if include_payload else "id, match_id, source, ingested_at"
    q = f"SELECT {select_cols} FROM deliveries"
    params = []
    clauses = []
    if since:
        clauses.append("ingested_at > ?")
        params.append(since)
    if match_id is not None:
        clauses.append("match_id = ?")
        params.append(match_id)
    if source:
        clauses.append("source = ?")
        params.append(source)
    if clauses:
        q += " WHERE " + " AND ".join(clauses)
    q += " ORDER BY ingested_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cur.execute(q, params)
    rows = []
    for r in cur.fetchall():
        if include_payload:
            id_, mid, src, payload_json, ingested_at = r
            try:
                payload = json.loads(payload_json)
            except Exception:
                payload = payload_json
            rows.append({
                "id": id_,
                "match_id": mid,
                "source": src,
                "payload": payload,
                "ingested_at": ingested_at
            })
        else:
            id_, mid, src, ingested_at = r
            rows.append({
                "id": id_,
                "match_id": mid,
                "source": src,
                "ingested_at": ingested_at
            })
    return rows
