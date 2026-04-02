from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from pathlib import Path
import shutil

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split

# ==== Script Args/Config ====
class Args:
    train_csv = "data/processed/combinedWithOdds.csv"
    out_dir = "models/weekly/homewin"
    test_size = 0.2
    random_state = 42
    n_matches_form = 5

args = Args()

# ==== Constants ====
COLUMNS_TO_KEEP: List[str] = [
    "Div","Date","Time","HomeTeam","AwayTeam","FTHG","FTAG","FTR","HTHG","HTAG","HTR",
    "Attendance","Referee","HS","AS","HST","AST","HHW","AHW","HC","AC","HF","AF","HFKC","AFKC",
    "HO","AO","HY","AY","HR","AR","1XBH","1XBD","1XBA","B365H","B365D","B365A","B365>2.5","B365<2.5",
    "B365AHH","B365AHA","B365AH","BFH","BFD","BFA","BFEH","BFED","BFEA","BFDH","BFDD","BFDA",
    "BMGMH","BMGMD","BMGMA","BVH","BVD","BVA","VCH","VCD","VCA","BSH","BSD","BSA","BWH","BWD","BWA",
    "CLH","CLD","CLA","GBH","GBD","GBA","GB>2.5","GB<2.5","GBAHH","GBAHA","GBAH","IWH","IWD","IWA",
    "LBH","LBD","LBA","LBAHH","LBAHA","LBAH","PSH","PH","PSD","PD","PSA","PA","P>2.5","P<2.5",
    "PAHH","PAHA","SOH","SOD","SOA","SBH","SBD","SBA","SJH","SJD","SJA","SYH","SYD","SYA","WHH","WHD","WHA",
    "Bb1X2","BbMxH","BbAvH","BbMxD","BbAvD","BbMxA","BbAvA","BbOU","BbMx>2.5","BbAv>2.5","BbMx<2.5","BbAv<2.5",
    "BbAH","BbAHh","BbMxAHH","BbAvAHH","BbMxAHA","BbAvAHA","MaxH","MaxD","MaxA","AvgH","AvgD","AvgA",
    "Max>2.5","Max<2.5","Avg>2.5","Avg<2.5","MaxAHH","MaxAHA","AvgAHH","AvgAHA","AHh"
]
COLS_TO_DROP_FOR_X: List[str] = [
    "FTR","HTR","HomeWin","HomeTeam","AwayTeam","Date","Referee","Season",
    "GoalsOver2_5","TotalGoals","FTHG","FTAG","HTHG","HTAG","HS","AS","HST","AST","HC","AC","HF","AF","HY","AY","HR","AR",
    "FTR_H","FTR_A","FTR_D","HTR_H","HTR_A","HTR_D",
    "HomeGoalDiff","AwayGoalDiff","HomePts","AwayPts","BTTS","Away_2plus","Home_2plus",
    "target_home_plus_two","target_away_plus_two",
]
ODDS_COLS: List[str] = [
    "B365H","B365D","B365A","B365>2.5","B365<2.5","B365AHH","B365AHA","B365AH",
    "IWH","IWD","IWA","WHH","WHD","WHA","PSH","PSD","PSA","PH","PD","PA","P>2.5","P<2.5","PAHH","PAHA",
    "LBH","LBD","LBA","LBAHH","LBAHA","LBAH",
    "GBH","GBD","GBA","GB>2.5","GB<2.5","GBAHH","GBAHA","GBAH",
    "BVH","BVD","BVA","VCH","VCD","VCA","1XBH","1XBD","1XBA","BWH","BWD","BWA","SOH","SOD","SOA",
    "SBH","SBD","SBA","CLH","CLD","CLA","BMGMH","BMGMD","BMGMA","BFDH","BFDD","BFDA","BFH","BFD","BFA","BFEH","BFED","BFEA",
    "SYH","SYD","SYA","SJH","SJD","SJA","BSH","BSD","BSA",
    "BbMxH","BbAvH","BbMxD","BbAvD","BbMxA","BbAvA","BbOU","BbMx>2.5","BbAv>2.5","BbMx<2.5","BbAv<2.5",
    "BbAH","BbAHh","BbMxAHH","BbAvAHH","BbMxAHA","BbAvAHA",
    "MaxH","MaxD","MaxA","AvgH","AvgD","AvgA","Max>2.5","Max<2.5","Avg>2.5","Avg<2.5",
    "MaxAHH","MaxAHA","AvgAHH","AvgAHA","AHh",
]
SCORE_COLS: List[str] = ["FTHG","FTAG","HTHG","HTAG","HS","AS","HST","AST","HC","AC","HF","AF","HY","AY","HR","AR"]
ESSENTIAL_ODDS: List[str] = ["B365H","B365D","B365A","WHH","WHD","WHA","IWH","IWD","IWA"]


def _parse_dates_series(date_series: pd.Series) -> pd.Series:
    out = pd.to_datetime(date_series, format="%d/%m/%y", errors="coerce")
    mask = out.isna()
    out.loc[mask] = pd.to_datetime(date_series.loc[mask], format="%d/%m/%Y", errors="coerce")
    return out


def clean_and_engineer_features(
    df: pd.DataFrame,
    columns_to_keep: List[str],
    *,
    fit_teams: bool,
    all_teams: Optional[List[str]] = None,
    n_matches: int = 5,
) -> Tuple[pd.DataFrame, List[str]]:
    df = df.copy()

    for col in columns_to_keep:
        if col not in df.columns:
            df[col] = np.nan
    df = df[columns_to_keep].copy()

    df = df[df["FTR"].notna()].copy()

    df["Date"] = _parse_dates_series(df["Date"])
    df = df[df["Date"] >= pd.Timestamp("2000-08-18")].reset_index(drop=True)

    df["HomeWin"] = (df["FTR"] == "H").astype(int)

    for col in ODDS_COLS + SCORE_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.drop_duplicates().reset_index(drop=True)

    essentials = [c for c in ESSENTIAL_ODDS if c in df.columns]
    df = df.dropna(subset=essentials).reset_index(drop=True)
    for col in ODDS_COLS:
        if col in df.columns:
            df[col] = df[col].fillna(df[col].mean())

    df = df.sort_values("Date").reset_index(drop=True)

    def get_season(dt: pd.Timestamp) -> str:
        y, m = dt.year, dt.month
        return f"{y}-{str(y+1)[-2:]}" if m >= 8 else f"{y-1}-{str(y)[-2:]}"

    new_cols = {
        "Season":             df["Date"].apply(get_season),
        "Year":               df["Date"].dt.year,
        "Month":              df["Date"].dt.month,
        "DayOfWeek":          df["Date"].dt.dayofweek,
        "HomeTeam_mean_FTHG": df.groupby("HomeTeam")["FTHG"].transform(
                                  lambda x: x.shift(1).expanding().mean()),
        "AwayTeam_mean_FTAG": df.groupby("AwayTeam")["FTAG"].transform(
                                  lambda x: x.shift(1).expanding().mean()),
    }
    df = pd.concat([df, pd.DataFrame(new_cols, index=df.index)], axis=1)

    base = df[["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]].copy()
    home_df = base[["Date", "HomeTeam", "FTHG", "FTAG"]].rename(
        columns={"HomeTeam": "Team", "FTHG": "GoalsFor", "FTAG": "GoalsAgainst"})
    away_df = base[["Date", "AwayTeam", "FTAG", "FTHG"]].rename(
        columns={"AwayTeam": "Team", "FTAG": "GoalsFor", "FTHG": "GoalsAgainst"})
    results = (
        pd.concat([home_df, away_df], ignore_index=True)
        .sort_values(["Team", "Date"])
        .reset_index(drop=True)
    )

    results["Points"] = np.where(
        results["GoalsFor"] > results["GoalsAgainst"], 3,
        np.where(results["GoalsFor"] == results["GoalsAgainst"], 1, 0)
    )
    results["RollingGF"] = results.groupby("Team")["GoalsFor"].transform(
        lambda x: x.shift(1).rolling(n_matches, min_periods=1).mean())
    results["RollingGA"] = results.groupby("Team")["GoalsAgainst"].transform(
        lambda x: x.shift(1).rolling(n_matches, min_periods=1).mean())
    results["RollingPoints"] = results.groupby("Team")["Points"].transform(
        lambda x: x.shift(1).rolling(n_matches, min_periods=1).sum())

    def last_form(team: str, dt: pd.Timestamp):
        row = results[(results["Team"] == team) & (results["Date"] < dt)].tail(1)
        if row.empty:
            return (np.nan, np.nan, np.nan)
        r = row.iloc[0]
        return (r["RollingGF"], r["RollingGA"], r["RollingPoints"])

    form_home = df.apply(
        lambda r: pd.Series(
            last_form(r["HomeTeam"], r["Date"]),
            index=["HomeRecentGF", "HomeRecentGA", "HomeRecentPts"]
        ),
        axis=1,
    )
    form_away = df.apply(
        lambda r: pd.Series(
            last_form(r["AwayTeam"], r["Date"]),
            index=["AwayRecentGF", "AwayRecentGA", "AwayRecentPts"]
        ),
        axis=1,
    )
    df = pd.concat([df, form_home, form_away], axis=1)

    df = df.dropna(subset=["HomeRecentGF", "AwayRecentGF"]).reset_index(drop=True)

    if fit_teams:
        teams = sorted(set(df["HomeTeam"]).union(set(df["AwayTeam"])))
    else:
        if all_teams is None:
            raise ValueError("all_teams must be provided when fit_teams=False")
        teams = all_teams

    home_team_cols = {f"HomeTeam_{t}": (df["HomeTeam"] == t).astype(int) for t in teams}
    away_team_cols = {f"AwayTeam_{t}": (df["AwayTeam"] == t).astype(int) for t in teams}
    df = pd.concat(
        [df,
         pd.DataFrame(home_team_cols, index=df.index),
         pd.DataFrame(away_team_cols, index=df.index)],
        axis=1,
    )

    df = df.replace([np.inf, -np.inf], np.nan)
    for col in df.select_dtypes(include=["number"]).columns:
        df[col] = df[col].fillna(df[col].median())

    df = df.loc[:, df.isnull().mean() < 0.95].copy()
    return df, teams


def sanitize_feature_names(cols: List[str]) -> List[str]:
    out = []
    seen = {}
    for c in cols:
        c2 = str(c).replace(">2.5", "_gt_2_5").replace("<2.5", "_lt_2_5")
        c2 = re.sub(r"[^\w]+", "_", c2).strip("_")
        if c2 in seen:
            seen[c2] += 1
            c2 = f"{c2}__{seen[c2]}"
        else:
            seen[c2] = 0
        out.append(c2)
    return out


def main():
    print("[train_homewin_weekly] settings:")
    print(json.dumps({k: v for k, v in vars(args).items()}, indent=2))

    train_path = Path(args.train_csv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df_raw = pd.read_csv(train_path, low_memory=False)
    df_clean, teams = clean_and_engineer_features(
        df_raw, COLUMNS_TO_KEEP, fit_teams=True, n_matches=args.n_matches_form
    )
    df_clean.to_csv("data/processed/engineered_train_features.csv", index=False)
    target = "HomeWin"
    X = df_clean.drop(columns=COLS_TO_DROP_FOR_X, errors="ignore")
    y = df_clean[target].astype(int)

    X = X.copy()
    X.columns = sanitize_feature_names(list(X.columns))
    X = X.select_dtypes(include=[np.number, "bool"])

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_size, random_state=args.random_state
    )

    model = LGBMClassifier(random_state=args.random_state)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    model_path = out_dir / f"lightgbm_homewin_{ts}.pkl"
    feat_path  = out_dir / f"feature_list_{ts}.pkl"
    meta_path  = out_dir / f"metadata_{ts}.json"

    joblib.dump(model, model_path)
    joblib.dump(list(X.columns), feat_path)

    meta = {
        "created_at_utc":    ts,
        "train_csv":         str(train_path),
        "rows_used":         int(len(df_clean)),
        "features":          int(X.shape[1]),
        "test_size":         args.test_size,
        "random_state":      args.random_state,
        "n_matches_form":    args.n_matches_form,
        "metrics":           {"accuracy": float(acc), "f1": float(f1)},
        "model_path":        str(model_path),
        "feature_list_path": str(feat_path),
        "teams_count":       len(teams),
        "python":            sys.version.splitlines()[0],
        "numpy":             np.__version__,
        "pandas":            pd.__version__,
    }
    meta_path.write_text(json.dumps(meta, indent=2))

    print(f"[train_homewin_weekly] rows={len(df_clean)} features={X.shape[1]}")
    print(f"[train_homewin_weekly] accuracy={acc:.4f} f1={f1:.4f}")
    print(f"[train_homewin_weekly] saved model         -> {model_path}")
    print(f"[train_homewin_weekly] saved feature list  -> {feat_path}")
    print(f"[train_homewin_weekly] saved metadata      -> {meta_path}")

    Path("artifacts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(meta_path, Path("artifacts/train_report.json"))
    print(f"[train_homewin_weekly] copied metadata      -> artifacts/train_report.json")


    print("\n[train_homewin_weekly] Feature columns used for training (in order):")
    for col in X.columns:
        print(col)

if __name__ == "__main__":
    main()
