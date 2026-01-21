from fastapi import FastAPI, HTTPException, Query, Header, Depends, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, validator
from typing import Optional, List
from pathlib import Path
import os
import sqlite3
from datetime import datetime

from .db import init_deliveries_db, insert_delivery, query_deliveries, exists_match_id, simple_query_deliveries

def require_api_key(x_api_key: Optional[str] = Header(None)):
    """
    If API_KEY env var is set, require a matching X-API-KEY header.
    If API_KEY is not set, the API is open.
    """
    api_key = os.environ.get("API_KEY")
    if api_key:
        if x_api_key != api_key:
            raise HTTPException(status_code=401, detail="Invalid X-API-KEY")
    return True

APP = FastAPI(title="Predictions Snapshot API", version="0.1")

# Simple health endpoint
@APP.get("/health")
def health():
    return {"status": "ok"}

DEFAULT_DB_PATH = os.environ.get("DELIVERIES_DB") or str(Path(__file__).resolve().parents[2] / "data" / "deliveries.db")
_deliveries_conn: Optional[sqlite3.Connection] = None

def get_deliveries_conn():
    global _deliveries_conn
    if _deliveries_conn is None:
        db_path = Path(DEFAULT_DB_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _deliveries_conn = init_deliveries_db(str(db_path))
    return _deliveries_conn

class IngestRow(BaseModel):
    match_id: int
    prob: Optional[float] = None
    home: Optional[str] = None
    away: Optional[str] = None
    odds_B365H: Optional[float] = None
    model_source: Optional[str] = None
    snapshot_created_at: Optional[str] = None

    @validator("prob")
    def prob_must_be_0_1(cls, v):
        if v is None:
            return v
        if not (0.0 <= v <= 1.0):
            raise ValueError("prob must be between 0.0 and 1.0")
        return v

class IngestPayload(BaseModel):
    rows: List[IngestRow]
    source: Optional[str] = None

@APP.post("/ingest")
def ingest(
    payload: IngestPayload = Body(...),
    _auth=Depends(require_api_key),
):
    """
    Accept payload and persist each validated row into deliveries DB.
    Application-level idempotency: skip any row if match_id already exists in deliveries (regardless of source).
    """
    rows = payload.rows
    if not rows or len(rows) == 0:
        raise HTTPException(status_code=400, detail="payload.rows must be a non-empty list")

    seen = set()
    for r in rows:
        if r.match_id in seen:
            raise HTTPException(status_code=400, detail=f"duplicate match_id in payload: {r.match_id}")
        seen.add(r.match_id)

    conn = get_deliveries_conn()
    persisted = 0
    skipped = 0
    errors = []

    received_at_now = datetime.utcnow().isoformat() + "Z"

    for idx, r in enumerate(rows):
        row_dict = r.dict()
        try:
            if exists_match_id(conn, r.match_id):
                skipped += 1
                continue

            ok = insert_delivery(conn, r.match_id, row_dict, payload.source, received_at=received_at_now)
            if ok:
                persisted += 1
            else:
                skipped += 1
        except Exception as e:
            errors.append({"index": idx, "match_id": getattr(r, "match_id", None), "error": str(e)})

    received = len(rows)
    response = {"received": received, "persisted": persisted, "skipped": skipped, "errors": errors, "source": payload.source}
    return JSONResponse(status_code=200, content=response)

@APP.get("/deliveries")
def deliveries(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    match_id: Optional[int] = Query(None),
    source: Optional[str] = Query(None),
    since: Optional[str] = Query(None, description="ISO timestamp filter (received_at > since)"),
    include_payload: bool = Query(True, description="Include full payload JSON in results"),
    simple: bool = Query(False, description="Return a compact, fast listing (id,match_id,source,received_at)"),
    _auth=Depends(require_api_key)
):
    """
    Return persisted deliveries with pagination and filters.
    If simple=true returns compact records (fast).
    """
    conn = get_deliveries_conn()
    try:
        if simple:
            rows = simple_query_deliveries(conn, limit=limit, offset=offset)
            return {"count": len(rows), "rows": rows, "limit": limit, "offset": offset}
        rows = query_deliveries(conn, limit=limit, offset=offset, since=since, match_id=match_id, source=source, include_payload=include_payload)
        return {"count": len(rows), "rows": rows, "limit": limit, "offset": offset}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query deliveries: {e}")
