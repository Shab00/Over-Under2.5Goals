#!/usr/bin/env python3
import pandas as pd
from pathlib import Path
import sys

# ---- CONFIG ----
ARCHIVE_DIR = Path("snapshots/archive")
RESULTS_SOURCE = Path("data/processed/combinedWithOdds.csv")
OUTPUT_FILE = Path("data/processed/results_merged.csv")

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
        all_preds["generated_at"] = pd.to_datetime(all_preds["generated_at"])
    else:
        all_preds["snapshot_ts"] = all_preds["snapshot_file"].str.extract(r"predictions_(\d{8}T\d{6})")
        all_preds["generated_at"] = pd.to_datetime(all_preds["snapshot_ts"], format="%Y%m%dT%H%M%S")

    all_preds["kickoff_dt"] = pd.to_datetime(all_preds["kickoff_time_utc"])

    all_preds = all_preds[all_preds["generated_at"] < all_preds["kickoff_dt"]].copy()

    all_preds.sort_values("generated_at", ascending=False, inplace=True)

    if "home_team" in all_preds.columns and "away_team" in all_preds.columns:
        all_preds["match_key"] = all_preds["kickoff_time_utc"].str[:10] + "|" + all_preds["home_team"] + "|" + all_preds["away_team"]
    else:
        all_preds["match_key"] = all_preds["Date"].str[:10] + "|" + all_preds["HomeTeam"] + "|" + all_preds["AwayTeam"]

    latest_preds = all_preds.drop_duplicates(subset="match_key", keep="first").copy()

    if not RESULTS_SOURCE.exists():
        print(f"[merge_results] Results file {RESULTS_SOURCE} not found – cannot merge.")
        sys.exit(1)

    results = pd.read_csv(RESULTS_SOURCE, low_memory=False)
    if "Date" in results.columns and "HomeTeam" in results.columns and "AwayTeam" in results.columns:
        results["match_key"] = results["Date"].astype(str).str[:10] + "|" + results["HomeTeam"] + "|" + results["AwayTeam"]
    else:
        print("[merge_results] Results file missing expected columns (Date, HomeTeam, AwayTeam).")
        sys.exit(1)

    merged = pd.merge(latest_preds, results[["match_key", "FTR", "FTHG", "FTAG"]], on="match_key", how="left")

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

    merged["profit"] = 0.0
    value_mask = merged["is_value"] & merged["FTR"].notna()
    merged.loc[value_mask & merged["correct"], "profit"] = merged.loc[value_mask & merged["correct"], "odds_B365H"] - 1
    merged.loc[value_mask & ~merged["correct"], "profit"] = -1.0

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(OUTPUT_FILE, index=False)
    print(f"[merge_results] Saved {len(merged)} rows to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
