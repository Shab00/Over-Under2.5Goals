#!/usr/bin/env python3
import datetime
import sys
from pathlib import Path
import pandas as pd

FIXTURES_FILE = Path("data/processed/updated_fixtures_with_odds.csv")

def main():
    if not FIXTURES_FILE.exists():
        print("::set-output name=should_run::false")
        print("[check] Fixture file not found – skipping.")
        sys.exit(0)

    df = pd.read_csv(FIXTURES_FILE, low_memory=False)
    if "Date" not in df.columns:
        print("::set-output name=should_run::false")
        print("[check] No 'Date' column – skipping.")
        sys.exit(0)

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    one_hour_ahead = now_utc + datetime.timedelta(hours=1)

    for _, row in df.iterrows():
        try:
            kickoff_naive = pd.to_datetime(row["Date"])
            kickoff_utc = kickoff_naive.tz_localize("UTC")
        except Exception:
            continue

        if now_utc <= kickoff_utc <= one_hour_ahead:
            print(f"[check] Match imminent: {row.get('HomeTeam','?')} vs {row.get('AwayTeam','?')} at {kickoff_utc}")
            print("::set-output name=should_run::true")
            sys.exit(0)

    print("::set-output name=should_run::false")
    print("[check] No matches within the next hour – skipping pipeline.")
    sys.exit(0)

if __name__ == "__main__":
    main()
