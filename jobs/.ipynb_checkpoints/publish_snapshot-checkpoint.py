from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests


IN_SNAPSHOT = Path(os.getenv("IN_SNAPSHOT", "artifacts/predictions_snapshot.csv"))
OUT_LATEST = Path(os.getenv("OUT_LATEST", "snapshots/predictions_latest.csv"))

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
API_KEY = os.getenv("API_KEY", "")


def _float_or_none(x):
    try:
        if x is None or x == "":
            return None
        return float(x)
    except Exception:
        return None


def main() -> int:
    if not IN_SNAPSHOT.exists():
        raise FileNotFoundError(f"[publish] missing input snapshot: {IN_SNAPSHOT}")

    OUT_LATEST.parent.mkdir(parents=True, exist_ok=True)

    # Read snapshot CSV from build step
    with IN_SNAPSHOT.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print(f"[publish] input snapshot has 0 rows: {IN_SNAPSHOT}")
        # still write header-only latest
        OUT_LATEST.write_text("match_id,kickoff_time_utc,home_team,away_team,prob_homewin,generated_at\n", encoding="utf-8")
        return 0

    generated_at = datetime.now(timezone.utc).isoformat()

    # Write canonical "latest" CSV (what the repo/pipeline expects)
    with OUT_LATEST.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "match_id",
            "kickoff_time_utc",
            "home_team",
            "away_team",
            "prob_homewin",
            "generated_at",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "match_id": r.get("match_id"),
                    "kickoff_time_utc": r.get("date"),  # you only have date (no time); OK for now
                    "home_team": r.get("home"),
                    "away_team": r.get("away"),
                    "prob_homewin": r.get("prob_home"),
                    "generated_at": generated_at,
                }
            )

    print(f"[publish] wrote {OUT_LATEST}")
    print(f"[publish] generated_at={generated_at}")

    # Ingest into API so Telegram pulls from /deliveries
    ingest_rows = []
    for r in rows:
        ingest_rows.append(
            {
                "match_id": r.get("match_id"),
                "prob": _float_or_none(r.get("prob_home")),
                "home": r.get("home"),
                "away": r.get("away"),
                "odds_B365H": _float_or_none(r.get("odds_B365H")),
                "model_source": r.get("model_source"),
                "snapshot_created_at": r.get("snapshot_created_at") or generated_at,
            }
        )

    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-KEY"] = API_KEY

    payload = {"rows": ingest_rows, "source": "weekly-pipeline"}
    try:
        resp = requests.post(f"{API_URL}/ingest", headers=headers, data=json.dumps(payload), timeout=30)
        print(f"[publish] POST {API_URL}/ingest -> {resp.status_code}")
        if resp.status_code >= 400:
            print("[publish] response:", resp.text[:800])
        resp.raise_for_status()
    except Exception as e:
        # Fail hard so cron alerts you
        raise RuntimeError(f"[publish] ingest failed: {e}") from e

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
