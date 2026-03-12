from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd


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


def load_feature_list(models_dir: Path) -> tuple[list[str], Path]:
    p = next(models_dir.glob("feature_list_*.pkl"), None)
    if p is None:
        raise FileNotFoundError(f"No feature_list_*.pkl found in {models_dir}")
    feat = joblib.load(p)
    if not isinstance(feat, (list, tuple)):
        feat = list(feat)
    return list(feat), p


def find_model(models_dir: Path) -> Path:
    lgb = next(models_dir.glob("*lightgbm*.pkl"), None)
    xgb = next(models_dir.glob("*xgboost*.pkl"), None)
    candidate = lgb or xgb
    if candidate is None:
        # avoid accidentally picking feature_list/cols_to_drop pkl
        pkls = [p for p in models_dir.glob("*.pkl") if "feature_list_" not in p.name and "cols_to_drop_" not in p.name and "columns_to_keep_" not in p.name]
        candidate = pkls[0] if pkls else None
    if candidate is None:
        raise FileNotFoundError(f"No model .pkl found in {models_dir}")
    return candidate


def parse_dates_safe(df: pd.DataFrame, col: str = "Date") -> pd.Series:
    if col not in df.columns:
        raise RuntimeError(f"Date column '{col}' not present in dataframe")
    s = df[col].dropna().astype(str)
    # heuristic: mostly ISO yyyy-mm-dd
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

    models_dir = Path(os.getenv("MODELS_DIR", "models/thirdIterration/boost")).resolve()
    train_csv = Path(os.getenv("TRAIN_CSV", "data/processed/train_df_clean.csv")).resolve()
    # fallback: if you never saved train_df_clean, use combinedWithOdds as proxy for train_end_date
    train_fallback_csv = Path(os.getenv("TRAIN_FALLBACK_CSV", "data/processed/combinedWithOdds.csv")).resolve()
    eval_csv = Path(os.getenv("EVAL_CSV", "data/processed/eval_df_clean.csv")).resolve()

    out_path = Path(os.getenv("OUT_SNAPSHOT", "artifacts/predictions_snapshot.csv")).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    threshold = float(os.getenv("THRESHOLD", "0.5"))

    print("[snapshot] cwd:", root)
    print("[snapshot] MODELS_DIR:", models_dir)
    print("[snapshot] TRAIN_CSV:", train_csv)
    print("[snapshot] TRAIN_FALLBACK_CSV:", train_fallback_csv)
    print("[snapshot] EVAL_CSV:", eval_csv)
    print("[snapshot] OUT_SNAPSHOT:", out_path)

    if not models_dir.exists():
        raise FileNotFoundError(f"Models directory not found: {models_dir}")
    if not eval_csv.exists():
        raise FileNotFoundError(f"Eval CSV not found: {eval_csv}")

    feature_list_raw, feat_path = load_feature_list(models_dir)
    model_path = find_model(models_dir)
    model = joblib.load(model_path)

    print("[snapshot] loaded feature_list:", feat_path.name, "len:", len(feature_list_raw))
    print("[snapshot] loaded model:", model_path.name)

    # train end date
    if train_csv.exists():
        train_df = pd.read_csv(train_csv, low_memory=False)
        train_df["Date"] = parse_dates_safe(train_df, "Date")
        train_end_date = pd.to_datetime(train_df["Date"]).max()
        print("[snapshot] train_end_date(from TRAIN_CSV):", train_end_date)
    elif train_fallback_csv.exists():
        train_df = pd.read_csv(train_fallback_csv, low_memory=False)
        if "Date" in train_df.columns:
            train_df["Date"] = parse_dates_safe(train_df, "Date")
            train_end_date = pd.to_datetime(train_df["Date"]).max()
            print("[snapshot] train_end_date(from TRAIN_FALLBACK_CSV):", train_end_date)
        else:
            train_end_date = None
            print("[snapshot] WARNING: no Date in TRAIN_FALLBACK_CSV; will not filter prospective rows.")
    else:
        train_end_date = None
        print("[snapshot] WARNING: TRAIN_CSV not found; will not filter prospective rows.")

    eval_df = pd.read_csv(eval_csv, low_memory=False)
    eval_df["Date"] = parse_dates_safe(eval_df, "Date")

    if train_end_date is not None and pd.notnull(train_end_date):
        prospective = eval_df[pd.to_datetime(eval_df["Date"]) > train_end_date].reset_index(drop=True)
    else:
        prospective = eval_df.reset_index(drop=True)

    print("[snapshot] prospective rows:", prospective.shape[0])
    if prospective.shape[0] == 0:
        raise RuntimeError("No prospective rows found.")

    # Build X
    cols_to_drop_local = ["Time", "Attendance", "Div"]  # same as your notebook fallback
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

    out = pd.DataFrame(
        {
            "match_id": prospective["match_id"] if "match_id" in prospective.columns else prospective.index.astype(int),
            "date": pd.to_datetime(prospective["Date"]).dt.strftime("%Y-%m-%d"),
            "home": prospective["HomeTeam"] if "HomeTeam" in prospective.columns else "",
            "away": prospective["AwayTeam"] if "AwayTeam" in prospective.columns else "",
            "prob_home": probs,
            "pred_label": preds,
            "odds_B365H": prospective["B365H"] if "B365H" in prospective.columns else np.nan,
            "model_source": model_path.name,
            "snapshot_created_at": snapshot_created_at,
        }
    )

    out.to_csv(out_path, index=False)
    print("[snapshot] wrote", out_path, "rows:", len(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
