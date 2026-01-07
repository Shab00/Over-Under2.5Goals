from fastapi import FastAPI, HTTPException, Query, Header, Depends, Body
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, validator
from typing import Optional, List
from pathlib import Path
import os
import glob
import pandas as pd
import time

APP = FastAPI(title="Predictions Snapshot API", version="0.1")

_cached_df = None
_cached_path = None
_cached_mtime = None

def find_snapshot_path() -> Path:
    env_path = os.environ.get("SNAPSHOT_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    repo_root = Path(__file__).resolve().parents[2]
    candidates = sorted(glob.glob(str(repo_root / "results" / "predictions_snapshot_with_calibrated_probs*.csv")))
    if candidates:
        return Path(candidates[-1])

    candidates = sorted(glob.glob(str(repo_root / "data" / "processed" / "predictions_snapshot*.csv")))
    if candidates:
        return Path(candidates[-1])

    alt_paths = [
        repo_root / "notebooks" / "thirdIterration" / "results" / "predictions_snapshot_with_calibrated_probs.csv",
        repo_root / "data" / "processed" / "predictions_snapshot_20251109T143856Z.csv",
    ]
    for p in alt_paths:
        if p.exists():
            return p

    raise FileNotFoundError("No snapshot found. Place CSV under results/ or data/processed/ or set SNAPSHOT_PATH.")

def load_snapshot(force: bool = False) -> pd.DataFrame:
    global _cached_df, _cached_path, _cached_mtime
    path = find_snapshot_path()
    mtime = path.stat().st_mtime
    if force or _cached_df is None or _cached_path != str(path) or _cached_mtime != mtime:
        parse_dates = ["date"] if "date" in pd.read_csv(path, nrows=0).columns else []
        df = pd.read_csv(path, parse_dates=parse_dates, low_memory=False)
        df.columns = [c.strip() for c in df.columns]
        _cached_df = df
        _cached_path = str(path)
        _cached_mtime = mtime
    return _cached_df

def df_to_json_safe(df: pd.DataFrame):
    return df.where(pd.notnull(df), None).to_dict(orient="records")

def require_api_key(x_api_key: Optional[str] = Header(None)):
    api_key = os.environ.get("API_KEY")
    if api_key:
        if x_api_key != api_key:
            raise HTTPException(status_code=401, detail="Invalid X-API-KEY")
    return True

@APP.get("/health")
def health():
    return {"status": "ok"}

@APP.get("/predictions/info")
def predictions_info(_auth=Depends(require_api_key)):
    """
    Lightweight info endpoint to confirm which snapshot was loaded,
    how many rows it contains and which columns are present.
    """
    try:
        df = load_snapshot()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "snapshot_path": _cached_path,
        "rows": len(df),
        "columns": list(df.columns),
    }

@APP.get("/predictions/latest")
def predictions_latest(
    limit: Optional[int] = Query(None, ge=1),
    threshold: Optional[float] = Query(None, ge=0.0, le=1.0),
    prob_col: str = Query("prob_platt"),
    as_csv: bool = Query(False),
    _auth=Depends(require_api_key)
):
    try:
        df = load_snapshot()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    col_in_use = prob_col if prob_col in df.columns else ("prob_home" if "prob_home" in df.columns else None)
    if threshold is not None and col_in_use is None:
        raise HTTPException(status_code=400, detail=f"prob_col '{prob_col}' not available.")

    out_df = df.copy()
    if threshold is not None:
        out_df = out_df[out_df[col_in_use].astype(float) >= float(threshold)]

    total_count = len(out_df)
    if limit:
        out_df = out_df.head(limit)

    if as_csv:
        csv_text = out_df.to_csv(index=False)
        return PlainTextResponse(content=csv_text, media_type="text/csv")

    payload = {
        "snapshot_path": _cached_path,
        "returned_count": len(out_df),
        "total_count": total_count,
        "rows": df_to_json_safe(out_df)
    }

    try:
        content = jsonable_encoder(payload)
        return JSONResponse(content=content)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to encode response: {e}")

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
    Accept an envelope {"rows": [...], "source": "..."} from ETL jobs.

    Validation performed by Pydantic:
      - each row must include `match_id` (int)
      - if `prob` is provided it must be 0.0 <= prob <= 1.0

    Additional checks:
      - payload.rows must be non-empty
      - no duplicate match_id values within the payload

    NOTE: This handler currently accepts and validates the payload and returns a count.
    TODO: persist ingested rows to a server-side DB or deliveries table for auditing and idempotency.
    """
    rows = payload.rows
    if not rows or len(rows) == 0:
        raise HTTPException(status_code=400, detail="payload.rows must be a non-empty list")

    seen = set()
    for r in rows:
        if r.match_id in seen:
            raise HTTPException(status_code=400, detail=f"duplicate match_id in payload: {r.match_id}")
        seen.add(r.match_id)

    received = len(rows)


    return JSONResponse(status_code=200, content={"received": received, "source": payload.source})
