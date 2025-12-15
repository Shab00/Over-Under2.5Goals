"""
smoketest.py

Lightweight smoke test for predictions snapshot + calibration outputs.

Usage:
  python smoketest.py
  python smoketest.py --threshold 0.32 --prob-col prob_platt --bootstrap 2000

What it checks:
- Finds a predictions snapshot under data/processed/predictions_snapshot*.csv
- Prints first rows and columns
- Validates prob range and odds numeric conversion
- Checks for calibrated snapshot results/predictions_snapshot_with_calibrated_probs*.csv
- Checks for threshold sweep CSVs results/threshold_sweep_*.csv
- If actuals present, computes Brier scores for prob_home, prob_platt, prob_isotonic
- Optionally computes bootstrap CI for mean pnl_1unit (ROI) at a threshold
"""
import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss

def find_first(pattern):
    lst = glob.glob(pattern)
    if not lst:
        return None
    lst.sort()
    return lst[-1]

def print_header(s):
    print("\n" + "="*8 + " " + s + " " + "="*8)

def main():
    parser = argparse.ArgumentParser(description="Smoke test for predictions snapshot and calibration outputs")
    parser.add_argument("--snapshot", default=None, help="Path to snapshot CSV (auto-detect if not given)")
    parser.add_argument("--calibrated", default=None, help="Path to calibrated snapshot CSV (auto-detect if not given)")
    parser.add_argument("--threshold", type=float, default=None, help="Optional threshold to bootstrap ROI CI for (requires pnl_1unit column)")
    parser.add_argument("--prob-col", default="prob_platt", help="Probability column to use for thresholding")
    parser.add_argument("--bootstrap", type=int, default=1000, help="Bootstrap iterations for ROI CI")
    args = parser.parse_args()

    snapshot = args.snapshot or find_first("data/processed/predictions_snapshot*.csv")
    print_header("Repo / file checks")
    try:
        branch = os.popen("git rev-parse --abbrev-ref HEAD 2>/dev/null").read().strip()
        print("  git branch:", branch or "(no-git)")
    except Exception:
        print("  (git check failed)")

    if not snapshot:
        print("ERROR: No snapshot found at data/processed/predictions_snapshot*.csv")
        sys.exit(2)
    print("Found snapshot:", snapshot)

    print_header("Snapshot sample & columns")
    try:
        df = pd.read_csv(snapshot, low_memory=False)
    except Exception as e:
        print("ERROR: failed to read snapshot:", e)
        sys.exit(2)

    print("Snapshot rows:", len(df))
    print("Columns:", df.columns.tolist())
    sample_cols = [c for c in ["date","match_id","home","away","prob_home","odds_B365H","actual","prob_platt","prob_isotonic","pnl_1unit"] if c in df.columns]
    print("Sample columns shown:", sample_cols)
    if len(df) > 0:
        print(df[sample_cols].head().to_string(index=False))

    print_header("Basic sanity checks")
    ok = True
    if "prob_home" in df.columns:
        probs = pd.to_numeric(df["prob_home"], errors="coerce")
        print("prob_home min/max (ignoring NaN):", probs.min(), probs.max())
        if probs.min() < 0 or probs.max() > 1:
            print("  WARNING: prob_home values outside [0,1]")
            ok = False
    else:
        print("  WARNING: prob_home column not present")
        ok = False

    if "odds_B365H" in df.columns:
        odds = pd.to_numeric(df["odds_B365H"], errors="coerce")
        print("odds_B365H numeric count:", odds.notna().sum(), "missing/invalid:", odds.isna().sum())
        if odds.notna().sum() == 0:
            print("  WARNING: odds_B365H appears non-numeric or missing")
            ok = False
    else:
        print("  NOTE: odds_B365H column not present")

    for c in ("prob_platt","prob_isotonic"):
        if c in df.columns:
            vals = pd.to_numeric(df[c], errors="coerce")
            print(f"{c} min/max:", vals.min(), vals.max())
            if vals.min() < 0 or vals.max() > 1:
                print(f"  WARNING: {c} outside [0,1]")
                ok = False

    print_header("Calibration & sweep files")
    calibrated = args.calibrated or find_first("results/predictions_snapshot_with_calibrated_probs*.csv")
    if calibrated:
        print("Found calibrated snapshot:", calibrated)
    else:
        print("No calibrated snapshot found under results/ (may be fine if not run)")

    sweep_files = glob.glob("results/threshold_sweep_*.csv")
    if sweep_files:
        print("Threshold sweep files found:", sweep_files)
    else:
        print("No threshold sweep CSVs found in results/")

    plots = glob.glob("results/*.png")
    if plots:
        print("Plot files in results/:")
        for p in plots[:6]:
            print("  ", p)
    else:
        print("No plots found in results/")

    print_header("Brier score (if actuals present)")
    if "actual" in df.columns and df["actual"].notna().sum() > 0:
        known = df[df["actual"].notna()].copy()
        print("Known rows with actual:", len(known))
        for col in ("prob_home","prob_platt","prob_isotonic"):
            if col in known.columns:
                try:
                    br = brier_score_loss(known["actual"].astype(float), known[col].astype(float))
                    print(f"  {col} Brier: {br:.6f}")
                except Exception as e:
                    print(f"  failed to compute Brier for {col}: {e}")
    else:
        print("No actuals found in snapshot; cannot compute Brier.")

    if args.threshold is not None:
        t = args.threshold
        pc = args.prob_col
        print_header(f"Bootstrap ROI CI for threshold {t} using {pc}")
        if pc not in df.columns:
            print(f"Probability column {pc} not in snapshot")
        else:
            sel = df[df[pc].astype(float) >= float(t)]
            if sel.empty:
                print("No rows meet the threshold.")
            else:
                if "pnl_1unit" not in sel.columns:
                    print("pnl_1unit column not found; cannot bootstrap realized ROI")
                else:
                    pnl = pd.to_numeric(sel["pnl_1unit"], errors="coerce").dropna().values
                    n = len(pnl)
                    print(f"Selected rows: {n}; total_pnl: {pnl.sum():.3f}; mean ROI: {np.nanmean(pnl):.6f}")
                    if n < 10:
                        print("Warning: small sample size for bootstrap (n < 10); CI will be noisy")
                    B = max(100, args.bootstrap)
                    rng = np.random.default_rng(0)
                    means = []
                    for _ in range(B):
                        sample = rng.choice(pnl, size=n, replace=True)
                        means.append(np.nanmean(sample))
                    lo = np.percentile(means, 2.5)
                    hi = np.percentile(means, 97.5)
                    print(f"{B}-iter bootstrap 95% CI for mean pnl per bet: [{lo:.6f}, {hi:.6f}]")

    print_header("Smoke test result")
    if ok:
        print("Basic checks passed. If you expected calibration/sweep files, verify those exist under results/.")
    else:
        print("Some checks reported warnings; inspect above messages and fix data/format issues.")

if __name__ == "__main__":
    main()
