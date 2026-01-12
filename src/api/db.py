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
    Returns an sqlite3.Connection (row factory NOT set).
    """
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    cur = conn.cursor()
    cur.executescript(DDL)
    return conn

def insert_delivery(conn: sqlite3.Connection, match_id: Optional[int], payload: dict, source: Optional[str]) -> bool:
    """
    Insert a delivery row. Returns True if persisted; False if duplicate (skipped).
    Uses UNIQUE(match_id, source) to detect duplicates. If match_id is None we use NULL;
    UNIQUE on (NULL, source) will not match other NULLs in SQLite, so this works best when match_id is present.
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
        return False

def query_deliveries(conn: sqlite3.Connection, limit: int = 100, since: Optional[str] = None, match_id: Optional[int] = None) -> List[Dict]:
    """
    Return recent deliveries as list of dicts.
    - since: optional ISO timestamp string to filter ingested_at > since
    - match_id: optional to filter by match_id
    """
    cur = conn.cursor()
    q = "SELECT id, match_id, source, payload_json, ingested_at FROM deliveries"
    params = []
    clauses = []
    if since:
        clauses.append("ingested_at > ?")
        params.append(since)
    if match_id is not None:
        clauses.append("match_id = ?")
        params.append(match_id)
    if clauses:
        q += " WHERE " + " AND ".join(clauses)
    q += " ORDER BY ingested_at DESC LIMIT ?"
    params.append(limit)
    cur.execute(q, params)
    rows = []
    for r in cur.fetchall():
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
    return rows
