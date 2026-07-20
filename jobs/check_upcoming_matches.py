#!/usr/bin/env python3
import datetime
import sys
from pathlib import Path
import pandas as pd

FIXTURES_FILE = Path("data/processed/updated_fixtures_with_odds.csv")

def main():
    if not FIXTURES_FILE.exists():
        print("[check] Fixture file not found – skipping.")
        sys.exit(1)

    df = pd.read_csv(FIXTURES_FILE, low_memory=False)
    if "Date" not in df.columns:
        print("[check] No 'Date' column – skipping.")
        sys.exit(1)

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    # TEMPORARY – simulate now being 2026-08-21 19:00 UTC (1 hour before the first match)
    # now_utc = datetime.datetime(2026, 8, 21, 19, 0, 0, tzinfo=datetime.timezone.utc)
    one_hour_ahead = now_utc + datetime.timedelta(hours=1)

    for _, row in df.iterrows():
        try:
            kickoff_naive = pd.to_datetime(row["Date"])
            kickoff_utc = kickoff_naive.tz_localize("UTC")
        except Exception:
            continue

        if now_utc <= kickoff_utc <= one_hour_ahead:
            print(f"[check] Match imminent: {row.get('HomeTeam','?')} vs {row.get('AwayTeam','?')} at {kickoff_utc}")
            sys.exit(0)

    print("[check] No matches within the next hour – skipping pipeline.")
    sys.exit(1)

if __name__ == "__main__":
    main()
