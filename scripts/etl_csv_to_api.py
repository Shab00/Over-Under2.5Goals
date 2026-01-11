import argparse
import csv
import json
import logging
import os
import sqlite3
import sys
import time
from typing import Dict, Generator, Iterable, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_BATCH_SIZE = 100
DEFAULT_RETRY_TOTAL = 5
DEFAULT_RETRY_BACKOFF = 1.0  # base backoff in seconds
CHECKPOINT_DB = "etl_checkpoints.db"  # local checkpointing for idempotency/resume

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("etl_csv_to_api")

def build_session(retries: int = DEFAULT_RETRY_TOTAL, backoff: float = DEFAULT_RETRY_BACKOFF) -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST", "PUT", "PATCH"]),
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

def read_csv_rows(path: str, start: int = 0) -> Generator[Dict[str, str], None, None]:
    """
    Stream rows from CSV as dictionaries. 'start' is 0-based row number to resume.
    """
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader):
            if i < start:
                continue
            yield row

def init_checkpoint_db(path: str = CHECKPOINT_DB):
    conn = sqlite3.connect(path, isolation_level=None)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS etl_checkpoints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        csv_path TEXT NOT NULL,
        last_row_index INTEGER NOT NULL,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS ix_csv_path ON etl_checkpoints(csv_path)
    """)
    return conn

def get_last_index(conn: sqlite3.Connection, csv_path: str) -> int:
    cur = conn.cursor()
    cur.execute("SELECT last_row_index FROM etl_checkpoints WHERE csv_path = ?", (csv_path,))
    row = cur.fetchone()
    return row[0] if row else 0

def set_last_index(conn: sqlite3.Connection, csv_path: str, last_row_index: int):
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO etl_checkpoints (csv_path, last_row_index) VALUES (?, ?)
    ON CONFLICT(csv_path) DO UPDATE SET last_row_index = excluded.last_row_index, updated_at = CURRENT_TIMESTAMP
    """, (csv_path, last_row_index))

def normalize_row(row: Dict[str, str]) -> Dict:
    """
    Transform CSV row strings to API expected types.
    TODO: Implement final mapping to the API contract here.
          Example:
             - convert date strings to ISO format
             - ensure numeric columns are float/int
             - rename prob_platt -> prob
    """
    out = {}
    out["match_id"] = int(row.get("match_id")) if row.get("match_id") else None
    out["date"] = row.get("date")  # TODO: parse and timezone-normalize if needed
    out["home"] = row.get("home")
    out["away"] = row.get("away")
    if row.get("prob_platt"):
        out["prob"] = float(row["prob_platt"])
    elif row.get("prob_home"):
        out["prob"] = float(row["prob_home"])
    else:
        out["prob"] = None
    # add other relevant fields (odds, model_source, snapshot_created_at)
    out["odds_B365H"] = float(row["odds_B365H"]) if row.get("odds_B365H") else None
    out["model_source"] = row.get("model_source")
    out["snapshot_created_at"] = row.get("snapshot_created_at")
    # TODO: add any engineered features required by the API payload
    return out
def post_batch(session: requests.Session, api_url: str, api_key: Optional[str], batch: List[Dict], timeout: int = 30):
    """
    Post a single batch to the API.
    - api_url: endpoint that accepts a list of rows, e.g., POST /ingest
    - api_key: optional header for authentication
    TODO: adjust payload key names to the target API contract.
    """
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-KEY"] = api_key

    payload = {"rows": batch, "source": "snapshot_etl"}  # example envelope
    try:
        resp = session.post(api_url, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return True, resp.json()
    except requests.HTTPError as e:
        # Non-2xx: log and bubble up for retry/backoff by caller
        logger.error("HTTP error posting batch: %s %s", resp.status_code if 'resp' in locals() else None, getattr(resp, "text", ""))
        return False, getattr(e, "response", None)
    except Exception as e:
        logger.exception("Unexpected error posting batch: %s", e)
        return False, None

def etl_csv_to_api(csv_path: str,
                   api_url: str,
                   api_key: Optional[str] = None,
                   batch_size: int = DEFAULT_BATCH_SIZE,
                   dry_run: bool = False,
                   checkpoint_db: Optional[str] = CHECKPOINT_DB):
    """
    Orchestrate reading CSV, normalizing, batching and posting to API.
    """
    logger.info("ETL start: csv=%s api=%s batch_size=%d dry_run=%s checkpoint_db=%s",
                csv_path, api_url, batch_size, dry_run, checkpoint_db)
    session = build_session()

    conn = init_checkpoint_db(checkpoint_db) if checkpoint_db else None
    start_index = get_last_index(conn, csv_path) if conn else 0
    logger.info("Resuming from row index: %d", start_index)

    batch = []
    sent = 0
    failed_batches = 0
    last_success_index = start_index

    for i, raw_row in enumerate(read_csv_rows(csv_path, start=start_index)):
        current_index = start_index + i
        try:
            row = normalize_row(raw_row)
        except Exception as e:
            logger.exception("Skipping row %d due to normalization error: %s", current_index, e)
            continue

        # TODO: add dedup/idempotency logic here (e.g., skip if match_id already delivered)
        batch.append(row)

        if len(batch) >= batch_size:
            logger.info("Posting batch ending at CSV index %d (size=%d)", current_index, len(batch))
            if dry_run:
                logger.info("Dry-run: would POST %d rows", len(batch))
                sent += len(batch)
                last_success_index = current_index + 1
                batch = []
                continue

            ok, resp = post_batch(session, api_url, api_key, batch)
            if ok:
                sent += len(batch)
                last_success_index = current_index + 1
                if conn:
                    set_last_index(conn, csv_path, last_success_index)
                logger.info("Batch posted successfully. total_sent=%d", sent)
            else:
                failed_batches += 1
                logger.error("Batch failed to post at index %d. failed_batches=%d", current_index, failed_batches)
                # TODO: decide on failure policy: retry loop, exponential backoff, or abort run
                # For now: sleep and retry once, then continue (simple backoff)
                time.sleep(5)
                ok2, resp2 = post_batch(session, api_url, api_key, batch)
                if ok2:
                    sent += len(batch)
                    last_success_index = current_index + 1
                    if conn:
                        set_last_index(conn, csv_path, last_success_index)
                    logger.info("Batch retry succeeded. total_sent=%d", sent)
                else:
                    logger.error("Batch retry also failed. Skipping batch; see logs for details.")
            batch = []

    if batch:
        logger.info("Posting final batch (size=%d)", len(batch))
        if dry_run:
            logger.info("Dry-run: final batch would be POSTed")
            sent += len(batch)
            last_success_index += len(batch)
            if conn:
                set_last_index(conn, csv_path, last_success_index)
        else:
            ok, resp = post_batch(session, api_url, api_key, batch)
            if ok:
                sent += len(batch)
                last_success_index += len(batch)
                if conn:
                    set_last_index(conn, csv_path, last_success_index)
            else:
                logger.error("Final batch failed to post")

    logger.info("ETL completed: sent=%d failed_batches=%d", sent, failed_batches)
    if conn:
        conn.close()
    return {"sent": sent, "failed_batches": failed_batches}

def parse_args():
    p = argparse.ArgumentParser(description="ETL: push CSV predictions to API (batching, retry, checkpoint)")
    p.add_argument("--csv", required=True, help="Path to predictions CSV snapshot")
    p.add_argument("--api-url", required=True, help="Destination API ingest URL (e.g., http://host:8000/ingest)")
    p.add_argument("--api-key", required=False, help="Optional API key for X-API-KEY header (or set API_KEY env)")
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    p.add_argument("--dry-run", action="store_true", help="Run without actually posting to the API")
    p.add_argument("--checkpoint-db", default=CHECKPOINT_DB, help="Path to local sqlite checkpoint DB")
    p.add_argument("--start", type=int, default=0, help="CSV start row (for manual resume)")
    p.add_argument("--no-checkpoint", action="store_true", help="Do not use checkpoint DB (process from start and do not persist progress)")
    p.add_argument("--force", action="store_true", help="Reset checkpoint for this CSV to 0 before running (use with checkpointing)")
    return p.parse_args()

def main():
    args = parse_args()
    api_key = args.api_key or os.environ.get("API_KEY")

    if args.no_checkpoint:
        checkpoint_db = None
    else:
        checkpoint_db = args.checkpoint_db

    if args.force and checkpoint_db:
        logger.info("Force reset: initializing checkpoint DB %s and setting last_row_index=0 for %s", checkpoint_db, args.csv)
        conn = init_checkpoint_db(checkpoint_db)
        set_last_index(conn, args.csv, 0)
        conn.close()

    result = etl_csv_to_api(
        csv_path=args.csv,
        api_url=args.api_url,
        api_key=api_key,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        checkpoint_db=checkpoint_db,
    )
    logger.info("Result: %s", result)

if __name__ == "__main__":
    main()
