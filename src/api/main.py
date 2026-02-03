from fastapi import FastAPI, HTTPException, Query, Header, Depends, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, validator
from typing import Optional, List
from pathlib import Path
import os
import sqlite3
from datetime import datetime

from .db import (
    init_deliveries_db,
    insert_delivery,
    query_deliveries,
    exists_match_id,
    simple_query_deliveries,
)

# Diagnostic: print when this module is imported (helps confirm running process)
print("[MODULE LOAD] src.api.main imported", flush=True)


def require_api_key(x_api_key: Optional[str] = Header(None)):
    api_key = os.environ.get("API_KEY")
    if api_key:
        if x_api_key != api_key:
            raise HTTPException(status_code=401, detail="Invalid X-API-KEY")
    return True


APP = FastAPI(title="Predictions Snapshot API", version="0.1")


@APP.get("/health")
def health():
    return {"status": "ok"}


DEFAULT_DB_PATH = os.environ.get("DELIVERIES_DB") or str(
    Path(__file__).resolve().parents[2] / "data" / "deliveries.db"
)
_deliveries_conn: Optional[sqlite3.Connection] = None


def get_deliveries_conn():
    global _deliveries_conn
    if _deliveries_conn is None:
        db_path = Path(DEFAULT_DB_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # Diagnostic: print which DB path we open
        print(f"[DB PATH] opening deliveries DB at: {db_path}", flush=True)
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

    # default source used when payload.source is omitted
    default_source = "api-ingest"
    # value we'll report back in the response
    response_source = payload.source or default_source

    for idx, r in enumerate(rows):
        row_dict = r.dict()
        try:
            print(f"[INGEST] idx={idx} match_id={r.match_id} - checking exists...", flush=True)
            exists = exists_match_id(conn, r.match_id)
            print(f"[INGEST] idx={idx} match_id={r.match_id} - exists_match_id -> {exists}", flush=True)
            if exists:
                skipped += 1
                print(f"[INGEST] idx={idx} match_id={r.match_id} - skipped because exists", flush=True)
                continue

            source_to_use = payload.source or default_source
            if payload.source is None:
                print(f"[INGEST] idx={idx} match_id={r.match_id} - payload.source omitted; using default '{source_to_use}'", flush=True)

            print(f"[INGEST] idx={idx} match_id={r.match_id} - attempting insert with source={source_to_use}", flush=True)
            ok = insert_delivery(conn, r.match_id, row_dict, source_to_use, received_at=received_at_now)
            print(f"[INGEST] idx={idx} match_id={r.match_id} - insert_delivery returned: {ok}", flush=True)

            if ok:
                persisted += 1
                print(f"[INGEST] idx={idx} match_id={r.match_id} - persisted", flush=True)
            else:
                skipped += 1
                print(f"[INGEST] idx={idx} match_id={r.match_id} - insert treated as duplicate/skip", flush=True)
        except Exception as e:
            errors.append({"index": idx, "match_id": getattr(r, "match_id", None), "error": str(e)})
            import traceback as _tb
            print(f"[INGEST] idx={idx} match_id={getattr(r, 'match_id', None)} - exception: {e}", flush=True)
            _tb.print_exc()

    received = len(rows)
    response = {"received": received, "persisted": persisted, "skipped": skipped, "errors": errors, "source": response_source}
    return JSONResponse(status_code=200, content=response)


@APP.get("/_debug/exists/{match_id}")
def _debug_exists(match_id: int):
    """
    Debug endpoint — returns the server's DEFAULT_DB_PATH and whether the server
    believes a given match_id exists in the deliveries DB.
    """
    conn = get_deliveries_conn()
    try:
        exists = exists_match_id(conn, match_id)
        return {"DEFAULT_DB_PATH": DEFAULT_DB_PATH, "match_id": match_id, "exists": exists}
    except Exception as e:
        return {"DEFAULT_DB_PATH": DEFAULT_DB_PATH, "match_id": match_id, "error": str(e)}


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
    conn = get_deliveries_conn()
    try:
        if simple:
            rows = simple_query_deliveries(conn, limit=limit, offset=offset)
            return {"count": len(rows), "rows": rows, "limit": limit, "offset": offset}
        rows = query_deliveries(conn, limit=limit, offset=offset, since=since, match_id=match_id, source=source, include_payload=include_payload)
        return {"count": len(rows), "rows": rows, "limit": limit, "offset": offset}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query deliveries: {e}")
