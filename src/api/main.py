from fastapi import FastAPI, HTTPException, Query, Header, Depends, Body
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, validator
from typing import Optional, List
from pathlib import Path
import os
import sqlite3
from datetime import datetime
import logging
import pandas as pd
import numpy as np
import time

from dotenv import load_dotenv
load_dotenv()
from src.metrics import (
    add_prometheus_metrics,
    ingestion_counter,
    smoke_test_runs,
    PIPELINE_RUNS,
    SNAPSHOT_AGE_SECONDS,
    PREDICTIONS_GENERATED,
    ODDS_AVAILABLE,
)

# basic logger
logger = logging.getLogger("api")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

from .db import (
    init_deliveries_db,
    insert_delivery,
    query_deliveries,
    exists_match_id,
    simple_query_deliveries,
)


def require_api_key(x_api_key: Optional[str] = Header(None)):
    api_key = os.environ.get("API_KEY")
    if api_key:
        if x_api_key != api_key:
            raise HTTPException(status_code=401, detail="Invalid X-API-KEY")
    return True


app = FastAPI(title="Predictions Snapshot API", version="0.1")
add_prometheus_metrics(app)


# ============================================================
# Override /metrics to include dynamic snapshot gauges
# ============================================================

@app.get("/metrics")
async def metrics():
    snapshot_path = "snapshots/predictions_latest.csv"
    if Path(snapshot_path).exists():
        mtime = Path(snapshot_path).stat().st_mtime
        SNAPSHOT_AGE_SECONDS.set(time.time() - mtime)
        try:
            df = pd.read_csv(snapshot_path)
            PREDICTIONS_GENERATED.set(len(df))
            if "odds_B365H" in df.columns:
                ODDS_AVAILABLE.set(df["odds_B365H"].notna().sum())
        except Exception:
            pass
    else:
        SNAPSHOT_AGE_SECONDS.set(-1)

    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ============================================================
# New endpoint: called by the pipeline after a successful run
# ============================================================

@app.post("/update_metrics")
async def update_metrics():
    """Called by the pipeline after a successful run."""
    PIPELINE_RUNS.inc()
    snapshot_path = "snapshots/predictions_latest.csv"
    if Path(snapshot_path).exists():
        mtime = Path(snapshot_path).stat().st_mtime
        SNAPSHOT_AGE_SECONDS.set(time.time() - mtime)
        try:
            df = pd.read_csv(snapshot_path)
            PREDICTIONS_GENERATED.set(len(df))
            if "odds_B365H" in df.columns:
                ODDS_AVAILABLE.set(df["odds_B365H"].notna().sum())
        except Exception:
            pass
    return {"status": "ok"}


# ============================================================
# Existing endpoints
# ============================================================

@app.get("/smoke/ok")
def smoke_ok():
    """
    lightweight smoke endpoint for quick health checks.
    increments a prometheus counter so we can verify scrape + basic request path.
    """
    try:
        smoke_test_runs.labels(kind="api", result="success").inc()
    except Exception:
        pass
    return {"ok": True}


default_db_path = (
    os.environ.get("DELIVERIES_DB")
    or os.environ.get("SQLITE_DB")
    or str(Path(__file__).resolve().parents[2] / "data" / "deliveries.db")
)

_deliveries_conn: Optional[sqlite3.Connection] = None


def get_deliveries_conn():
    """
    return a cached sqlite3.Connection for the deliveries db.
    the connection is initialized lazily and created with init_deliveries_db(path).
    """
    global _deliveries_conn
    if _deliveries_conn is None:
        db_path = Path(default_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Opening deliveries DB at %s", str(db_path))
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


@app.post("/ingest")
def ingest(
    payload: IngestPayload = Body(...),
    _auth=Depends(require_api_key),
):
    """
    accept payload and persist each validated row into deliveries db.
    application-level idempotency: skip any row if match_id already exists in deliveries (regardless of source).
    """
    rows = payload.rows
    if not rows or len(rows) == 0:
        try:
            smoke_test_runs.labels(kind="api", result="error").inc()
        except Exception:
            pass
        raise HTTPException(status_code=400, detail="payload.rows must be a non-empty list")

    seen = set()
    for r in rows:
        if r.match_id in seen:
            try:
                smoke_test_runs.labels(kind="api", result="error").inc()
            except Exception:
                pass
            raise HTTPException(status_code=400, detail=f"duplicate match_id in payload: {r.match_id}")
        seen.add(r.match_id)

    conn = get_deliveries_conn()
    persisted = 0
    skipped = 0
    errors = []

    received_at_now = datetime.utcnow().isoformat() + "Z"

    default_source = "api-ingest"
    response_source = payload.source or default_source

    for idx, r in enumerate(rows):
        row_dict = r.dict()
        try:
            exists = exists_match_id(conn, r.match_id)
            if exists:
                skipped += 1
                try:
                    ingestion_counter.labels(result="skipped", source=payload.source or default_source).inc()
                except Exception:
                    pass
                continue

            source_to_use = payload.source or default_source

            ok = insert_delivery(conn, r.match_id, row_dict, source_to_use, received_at=received_at_now)

            if ok:
                persisted += 1
                try:
                    ingestion_counter.labels(result="persisted", source=source_to_use).inc()
                except Exception:
                    pass
            else:
                skipped += 1
                try:
                    ingestion_counter.labels(result="skipped", source=source_to_use).inc()
                except Exception:
                    pass
        except Exception as e:
            errors.append({"index": idx, "match_id": getattr(r, "match_id", None), "error": str(e)})
            try:
                ingestion_counter.labels(result="error", source=payload.source or default_source).inc()
            except Exception:
                pass

    received = len(rows)
    response = {
        "received": received,
        "persisted": persisted,
        "skipped": skipped,
        "errors": errors,
        "source": response_source,
    }

    try:
        smoke_test_runs.labels(kind="api", result="success").inc()
    except Exception:
        pass

    return JSONResponse(status_code=200, content=response)


@app.get("/deliveries")
def deliveries(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    match_id: Optional[int] = Query(None),
    source: Optional[str] = Query(None),
    since: Optional[str] = Query(None, description="ISO timestamp filter (received_at > since)"),
    include_payload: bool = Query(True, description="include full payload JSON in results"),
    simple: bool = Query(False, description="return a compact, fast listing (id,match_id,source,received_at)"),
    _auth=Depends(require_api_key),
):
    conn = get_deliveries_conn()
    try:
        if simple:
            rows = simple_query_deliveries(conn, limit=limit, offset=offset)
            return {"count": len(rows), "rows": rows, "limit": limit, "offset": offset}
        rows = query_deliveries(
            conn,
            limit=limit,
            offset=offset,
            since=since,
            match_id=match_id,
            source=source,
            include_payload=include_payload,
        )
        return {"count": len(rows), "rows": rows, "limit": limit, "offset": offset}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query deliveries: {e}")


predictions_csv = (
    os.environ.get("PREDICTIONS_LATEST_CSV")
    or str(Path(__file__).resolve().parents[2] / "artifacts" / "premier_league_2025_26_predictions.csv")
)


@app.get("/predictions/latest")
def get_latest_predictions(_auth=Depends(require_api_key)):
    """
    serve the latest predictions snapshot as JSON.
    """
    try:
        df = pd.read_csv(predictions_csv)
        df = df.replace([np.nan, np.inf, -np.inf], None)
        records = df.to_dict(orient="records")
        mtime = os.path.getmtime(predictions_csv)
        updated_at = datetime.utcfromtimestamp(mtime).isoformat() + "Z"
        return {"predictions": records, "updated_at": updated_at}
    except Exception as e:
        logger.error(f"Failed to load predictions: {e}")
        raise HTTPException(status_code=500, detail=str(e))
