from fastapi import FastAPI, HTTPException, Query, Header, Depends, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, validator
from typing import Optional, List
from pathlib import Path
import os
import sqlite3
from datetime import datetime

from .db import init_deliveries_db, insert_delivery, query_deliveries, exists_match_id, simple_query_deliveries
print("[MODULE LOAD] src.api.main imported", flush=True)


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

@APP.get("/health")
def health():
    return {"status": "ok"}

DEFAULT_DB_PATH = os.environ.get("DELIVERIES_DB") or str(Path(__file__).resolve().parents[2] / "data" / "deliveries.db")
_deliveries_conn: Optional[sqlite3.Connection] = None
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
