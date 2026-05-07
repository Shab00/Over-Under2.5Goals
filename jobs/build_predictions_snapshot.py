from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
import re

def safe_colname(col: str) -> str:
    if not isinstance(col, str):
        col = str(col)
    return (
        col.replace(">", "_gt_")
        .replace("<", "_lt_")
        .replace("[", "_")
        .replace("]", "_")
        .replace("/", "_")
        .replace(" ", "_")
        .replace("%", "pct")
        .replace(".", "_")
    )

def _extract_timestamp(filename: str) -> str:
    m = re.search(r"_(\d{8}T\d{6}Z)", filename)
    return m.group(1) if m else ""

def find_latest_model_and_featurelist(models_dir: Path) -> tuple[Path, Path]:
    feats = list(models_dir.glob("feature_list_*.pkl"))
    mods  = list(models_dir.glob("lightgbm_homewin_*.pkl"))
    feat_dict = {_extract_timestamp(p.name): p for p in feats}
    mod_dict  = {_extract_timestamp(p.name): p for p in mods}
    common = sorted(set(feat_dict) & set(mod_dict), reverse=True)
    if not common:
        raise FileNotFoundError("No matching feature_list/model pairs in {}".format(models_dir))
    ts = common[0]
    return mod_dict[ts], feat_dict[ts]

def parse_dates_safe(df: pd.DataFrame, col: str = "Date") -> pd.Series:
    if col not in df.columns:
        raise RuntimeError(f"Date column '{col}' not present in dataframe")
    s = df[col].dropna().astype(str)
    if (s.str.match(r"^\d{4}-\d{2}-\d{2}").sum() > len(s) * 0.6) if len(s) else False:
        return pd.to_datetime(df[col], errors="coerce", dayfirst=False)
    parsed = pd.to_datetime(df[col], errors="coerce", dayfirst=True)
    mask = parsed.isna()
    if mask.any():
        parsed.loc[mask] = pd.to_datetime(df.loc[mask, col].astype(str), errors="coerce", dayfirst=False)
    return parsed

def dedupe_preserve_order(seq: list[str]) -> list[str]:
    seen = set()
    out: list[str] = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

def merge_duplicate_columns(df: pd.DataFrame) -> pd.DataFrame:
    dup = df.columns[df.columns.duplicated()].unique()
    if len(dup) == 0:
        return df
    # average duplicates
    return df.T.groupby(level=0).mean().T

def main() -> int:
    root = Path.cwd()
    models_dir = Path("models/weekly/homewin").resolve()
    eval_csv = Path("data/processed/premier_league_2025_26_upcoming_with_teams_and_date.csv").resolve()
    out_path = Path("artifacts/premier_league_2025_26_predictions.csv").resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    threshold = float(os.getenv("THRESHOLD", "0.5"))

    print("[snapshot] cwd:", root)
    print("[snapshot] MODELS_DIR:", models_dir)
    print("[snapshot] EVAL_CSV:", eval_csv)
    print("[snapshot] OUT_SNAPSHOT:", out_path)

    if not models_dir.exists():
        raise FileNotFoundError(f"Models directory not found: {models_dir}")
    if not eval_csv.exists():
        raise FileNotFoundError(f"Eval CSV not found: {eval_csv}")

    model_path, feat_path = find_latest_model_and_featurelist(models_dir)
    feature_list_raw = joblib.load(feat_path)
    model = joblib.load(model_path)

    print("[snapshot] loaded feature_list:", feat_path.name, "len:", len(feature_list_raw))
    print("[snapshot] loaded model:", model_path.name)

    eval_df = pd.read_csv(eval_csv, low_memory=False)
    eval_df["Date"] = parse_dates_safe(eval_df, "Date")
    prospective = eval_df.reset_index(drop=True)
    print("[snapshot] games for prediction:", prospective.shape[0])
    if prospective.shape[0] == 0:
        raise RuntimeError("No prospective rows found.")

    cols_to_drop_local = ["Time", "Attendance", "Div"]
    X_eval = prospective.drop(columns=cols_to_drop_local, errors="ignore").copy()

    X_eval.columns = [safe_colname(c) for c in X_eval.columns]
    feature_list_norm = dedupe_preserve_order([safe_colname(f) for f in feature_list_raw])

    X_eval = X_eval.apply(pd.to_numeric, errors="coerce")

    dup = X_eval.columns[X_eval.columns.duplicated()].unique()
    if len(dup):
        print("[snapshot] merging duplicate columns:", list(dup)[:10])
        X_eval = merge_duplicate_columns(X_eval)

    missing_feats = [f for f in feature_list_norm if f not in X_eval.columns]
    if missing_feats:
        print(f"[snapshot] {len(missing_feats)} features missing; filling with 0. Examples:", missing_feats[:10])

    X_eval = X_eval.reindex(columns=feature_list_norm, fill_value=0).fillna(0)

    # Predict
    if hasattr(model, "predict_proba"):
        probs = model.predict_proba(X_eval.values)[:, 1]
    else:
        probs = model.predict(X_eval.values).astype(float)

    preds = (probs >= threshold).astype(int)

    snapshot_created_at = datetime.now(timezone.utc).isoformat()

    out = pd.DataFrame({
        "match_id": prospective["match_id"] if "match_id" in prospective.columns else prospective.index.astype(int),
        "date": pd.to_datetime(prospective["Date"]).dt.strftime("%Y-%m-%d"),
        "home": prospective["HomeTeam"] if "HomeTeam" in prospective.columns else "",
        "away": prospective["AwayTeam"] if "AwayTeam" in prospective.columns else "",
        "prob_home": probs,
        "pred_label": preds,
        "odds_B365H": prospective["B365H"] if "B365H" in prospective.columns else np.nan,
        "model_source": model_path.name,
        "featurelist_source": feat_path.name,
        "snapshot_created_at": snapshot_created_at,
    })

    out.to_csv(out_path, index=False)
    print("[snapshot] wrote", out_path, "rows:", len(out))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
