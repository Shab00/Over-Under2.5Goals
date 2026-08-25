#!/usr/bin/env python3
import pandas as pd
import re
from pathlib import Path
import sys

# ---- CONFIG ----
ARCHIVE_DIR = Path("snapshots/archive")
RESULTS_SOURCE = Path("data/processed/combinedWithOdds.csv")
FIXTURES_SOURCE = Path("data/processed/updated_fixtures_with_odds.csv")
OUTPUT_FILE = Path("data/processed/results_merged.csv")

TEAM_MAP = {
    'manchester united': 'Man United',
    'man utd': 'Man United',
    'manchester city': 'Man City',
    'man city': 'Man City',
    'wolves': 'Wolves',
    'wolverhampton wanderers': 'Wolves',
    'nottingham forest': "Nott'm Forest",
    'west bromwich albion': 'West Brom',
    'west ham united': 'West Ham',
    'newcastle united': 'Newcastle',
    'tottenham hotspur': 'Tottenham',
    'tottenham': 'Tottenham',
    'spurs': 'Tottenham',
    'leeds united': 'Leeds',
    'leeds': 'Leeds',
    'leicester city': 'Leicester',
    'sheffield united': 'Sheffield United',
    'crystal palace': 'Crystal Palace',
    'aston villa': 'Aston Villa',
    'brighton & hove albion': 'Brighton',
    'brighton and hove albion': 'Brighton',
    'bournemouth': 'Bournemouth',
    'liverpool': 'Liverpool',
    'chelsea': 'Chelsea',
    'arsenal': 'Arsenal',
    'brentford': 'Brentford',
    'burnley': 'Burnley',
    'luton town': 'Luton',
    'fulham': 'Fulham',
    'everton': 'Everton',
    'coventry': 'Coventry City',
    'hull': 'Hull City',
    'ipswich': 'Ipswich Town',
    'sunderland': 'Sunderland',
    'nottm forest': "Nott'm Forest",
    'nott\'m forest': "Nott'm Forest",
    'palace': 'Crystal Palace',
}

def standardize_team(val):
    if pd.isna(val):
        return val
    t = str(val).strip().lower()
    t = re.sub(r'\s+', ' ', t)
    return TEAM_MAP.get(t, val if isinstance(val, str) else str(val))

def clean_team_names(df, cols=("HomeTeam", "AwayTeam")):
    for col in cols:
        if col in df.columns:
            df[col] = df[col].apply(standardize_team)
    return df

def load_fixture_times():
    if not FIXTURES_SOURCE.exists():
        return {}
    times = {}
    try:
        df = pd.read_csv(FIXTURES_SOURCE, low_memory=False)
        if "Date" not in df.columns or "HomeTeam" not in df.columns or "AwayTeam" not in df.columns:
            return {}
        df = clean_team_names(df, cols=("HomeTeam", "AwayTeam"))
        for _, row in df.iterrows():
            date_raw = str(row["Date"]).strip()
            home = row["HomeTeam"]
            away = row["AwayTeam"]
            try:
                kickoff_naive = pd.to_datetime(date_raw, dayfirst=False, errors="coerce")
                if pd.isna(kickoff_naive):
                    continue
                try:
                    import zoneinfo
                    uk_tz = zoneinfo.ZoneInfo("Europe/London")
                    kickoff_uk = kickoff_naive.tz_localize(uk_tz)
                except Exception:
                    import pytz
                    uk_tz = pytz.timezone("Europe/London")
                    kickoff_uk = uk_tz.localize(kickoff_naive.to_pydatetime())
                kickoff_utc = kickoff_uk.astimezone('UTC')
            except Exception:
                kickoff_utc = kickoff_naive.tz_localize('UTC')
            key = f"{kickoff_utc.strftime('%Y-%m-%d')}|{home}|{away}"
            times[key] = kickoff_utc
    except Exception as e:
        print(f"[merge_results] Warning: could not load fixture times: {e}")
    return times

def main():
    if not ARCHIVE_DIR.exists():
        print("[merge_results] No archive directory found – nothing to merge.")
        sys.exit(0)

    snapshots = []
    for f in sorted(ARCHIVE_DIR.glob("predictions_*.csv")):
        try:
            df = pd.read_csv(f)
            df["snapshot_file"] = f.name
            snapshots.append(df)
        except Exception as e:
            print(f"[merge_results] Skipping {f}: {e}")

    if not snapshots:
        print("[merge_results] No valid snapshot files found.")
        sys.exit(0)

    all_preds = pd.concat(snapshots, ignore_index=True)

    if "generated_at" in all_preds.columns:
        all_preds["generated_at"] = pd.to_datetime(all_preds["generated_at"], utc=True)
    else:
        all_preds["snapshot_ts"] = all_preds["snapshot_file"].str.extract(r"predictions_(\d{8}T\d{6})")
        all_preds["generated_at"] = pd.to_datetime(all_preds["snapshot_ts"], format="%Y%m%dT%H%M%S", utc=True)

    all_preds = clean_team_names(all_preds, cols=("home_team", "away_team"))

    fixture_times = load_fixture_times()

    kickoff_values = []
    for _, row in all_preds.iterrows():
        date_str = str(row["kickoff_time_utc"])[:10]
        home = row.get("home_team", "")
        away = row.get("away_team", "")
        key = f"{date_str}|{home}|{away}"
        kickoff_dt = fixture_times.get(key)
        if kickoff_dt is None:
            kickoff_dt = pd.to_datetime(date_str + " 23:59:59", errors="coerce").tz_localize("UTC")
        kickoff_values.append(kickoff_dt)
    all_preds["kickoff_dt"] = kickoff_values

    all_preds = all_preds[all_preds["generated_at"] < all_preds["kickoff_dt"]].copy()

    all_preds["match_key"] = (
        all_preds["kickoff_time_utc"].astype(str).str[:10]
        + "|" + all_preds["home_team"]
        + "|" + all_preds["away_team"]
    )

    all_preds.sort_values("generated_at", ascending=False, inplace=True)
    latest_preds = all_preds.drop_duplicates(subset="match_key", keep="first").copy()

    if not RESULTS_SOURCE.exists():
        print(f"[merge_results] Results file {RESULTS_SOURCE} not found – cannot merge.")
        sys.exit(1)

    results = pd.read_csv(RESULTS_SOURCE, low_memory=False)
    results = clean_team_names(results, cols=("HomeTeam", "AwayTeam"))

    if "Date" in results.columns:
        if "DateISO" in results.columns:
            results["date_str"] = results["DateISO"].astype(str).str[:10]
        else:
            results["date_str"] = pd.to_datetime(
                results["Date"], dayfirst=True, errors="coerce"
            ).dt.strftime("%Y-%m-%d")
    else:
        print("[merge_results] Results file missing Date column.")
        sys.exit(1)

    results["match_key"] = results["date_str"] + "|" + results["HomeTeam"] + "|" + results["AwayTeam"]

    merged = pd.merge(
        latest_preds,
        results[["match_key", "FTR", "FTHG", "FTAG"]],
        on="match_key",
        how="left"
    )

    merged = merged[merged["FTR"].notna() & (merged["FTR"].astype(str).str.strip() != "")]

    if "prob_homewin" in merged.columns:
        merged["prob_homewin"] = pd.to_numeric(merged["prob_homewin"], errors="coerce")
    else:
        merged["prob_homewin"] = merged.get("PHome", None)

    if "odds_B365H" in merged.columns:
        merged["odds_B365H"] = pd.to_numeric(merged["odds_B365H"], errors="coerce")

    merged["FTR"] = merged["FTR"].astype(str).str.strip()
    merged["home_win"] = merged["FTR"] == "H"
    merged["pred_win"] = merged["prob_homewin"] >= 0.5

    merged["correct"] = merged["home_win"] == merged["pred_win"]

    if "odds_B365H" in merged.columns and "prob_homewin" in merged.columns:
        merged["implied_prob"] = 1.0 / merged["odds_B365H"]
        merged["is_value"] = merged["prob_homewin"] > merged["implied_prob"]
    else:
        merged["is_value"] = False

    merged["value_correct"] = merged["is_value"] & merged["home_win"]

    merged["profit"] = 0.0
    value_mask = merged["is_value"]
    merged.loc[value_mask & merged["value_correct"], "profit"] = merged.loc[value_mask & merged["value_correct"], "odds_B365H"] - 1
    merged.loc[value_mask & ~merged["value_correct"], "profit"] = -1.0

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(OUTPUT_FILE, index=False)
    print(f"[merge_results] Saved {len(merged)} rows to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
