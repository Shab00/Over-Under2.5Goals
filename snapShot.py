#!/usr/bin/env python
# coding: utf-8

# In[6]:


import re
import joblib, json, sys, platform, subprocess
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter


# In[2]:


MODELS_DIR = Path.cwd().joinpath("../../models/thirdIterration/boost").resolve()
print("MODELS_DIR:", MODELS_DIR)
assert MODELS_DIR.exists(), f"Directory not found: {MODELS_DIR}"

lgb = next(MODELS_DIR.glob("*lightgbm*.pkl"), None)
xgb = next(MODELS_DIR.glob("*xgboost*.pkl"), None)
feat = next(MODELS_DIR.glob("feature_list_*.pkl"), None)
meta = next(MODELS_DIR.glob("metadata_*.json"), None)

print("Found:")
print("  LightGBM:", lgb)
print("  XGBoost :", xgb)
print("  Feature :", feat)
print("  Metadata:", meta)

if feat:
    feature_list = joblib.load(feat)
    print("Loaded feature list length:", len(feature_list))
else:
    feature_list = None
    print("No feature_list found.")


# In[4]:


ROOT = Path.cwd()
TRAIN_CSV = ROOT / "../../data/processed/train_df_clean.csv"
EVAL_CSV  = ROOT / "../../data/processed/eval_df_clean.csv"

print("Expecting:", TRAIN_CSV, EVAL_CSV)
assert TRAIN_CSV.exists(), f"Train CSV not found: {TRAIN_CSV}"
assert EVAL_CSV.exists(), f"Eval CSV not found: {EVAL_CSV}"

train_df_clean = pd.read_csv(TRAIN_CSV, low_memory=False)
eval_df_clean  = pd.read_csv(EVAL_CSV,  low_memory=False)

for df,name in [(train_df_clean,"train_df_clean"),(eval_df_clean,"eval_df_clean")]:
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        print(f"{name} Date min/max:", df['Date'].min(), df['Date'].max())
    else:
        raise RuntimeError(f"'Date' column missing in {name}")

print("Shapes -> train:", train_df_clean.shape, " eval:", eval_df_clean.shape)
print("Eval sample:", eval_df_clean[['Date','HomeTeam','AwayTeam','B365H']].head().to_dict(orient='records'))


# In[7]:


eval_cols = list(eval_df_clean.columns)
print("Eval columns count:", len(eval_cols))
print("Feature list count:", len(feature_list))

missing_from_eval = [f for f in feature_list if f not in eval_cols]
eval_only = [c for c in eval_cols if c not in feature_list]

print("Training features missing in eval:", len(missing_from_eval))
print("Examples (up to 20):", missing_from_eval[:20])
print("Eval-only columns (not in feature_list):", len(eval_only))
print("Examples (up to 20):", eval_only[:20])

dup_eval = eval_df_clean.columns[eval_df_clean.columns.duplicated()].unique()
dup_feat = [f for f,c in Counter(feature_list).items() if c>1]
print("Duplicate column names in eval_clean:", list(dup_eval))
print("Duplicate names in feature_list:", dup_feat)

essential_odds = ['B365H','B365D','B365A','WHH','WHD','WHA','IWH','IWD','IWA']
print("Essential odds present in eval_clean:", [c for c in essential_odds if c in eval_df_clean.columns])


# In[8]:


OUT_DIR = Path.cwd() / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# infer train end date and select prospective rows
train_end_date = pd.to_datetime(train_df_clean['Date']).max()
print("train_end_date:", train_end_date)

prospective = eval_df_clean[pd.to_datetime(eval_df_clean['Date']) > train_end_date].reset_index(drop=True)
print("Prospective rows:", prospective.shape[0])
if prospective.shape[0] == 0:
    raise RuntimeError("No prospective rows found. Check Date parsing and train_end_date.")

# prepare X_eval
# drop any training-only columns you don't want as features (if you have a cols_to_drop list, set it)
try:
    cols_to_drop  # noqa: F821
except NameError:
    cols_to_drop = []  # set if needed
X_eval = prospective.drop(columns=cols_to_drop, errors='ignore').copy()

# safe normalization used at training time
X_eval.columns = [c.replace('[','_').replace(']','_').replace('<','_').replace('>','_') for c in X_eval.columns]
X_eval = X_eval.apply(pd.to_numeric, errors='coerce')

# merge duplicate columns (if any)
dup = X_eval.columns[X_eval.columns.duplicated()].unique()
if len(dup):
    print("Merging duplicate cols:", list(dup))
    X_eval = X_eval.groupby(level=0, axis=1).mean()

# dedupe feature_list order if necessary
feat_counts = Counter(feature_list)
if any(v>1 for v in feat_counts.values()):
    seen=set(); new_feat=[]
    for f in feature_list:
        if f not in seen:
            seen.add(f); new_feat.append(f)
    feature_list = new_feat
    print("Deduplicated feature_list length:", len(feature_list))

# align and fill missing features with 0
missing_feats = [f for f in feature_list if f not in X_eval.columns]
if missing_feats:
    print("Filling missing features with 0. Examples:", missing_feats[:10])
X_eval = X_eval.reindex(columns=feature_list, fill_value=0).fillna(0)

# predict probabilities
if hasattr(model, "predict_proba"):
    probs = model.predict_proba(X_eval.values)[:, 1]
else:
    preds = model.predict(X_eval.values)
    probs = preds.astype(float)

preds = (probs >= 0.5).astype(int)

# build snapshot
out = pd.DataFrame({
    "match_id": prospective.get("match_id", prospective.index.astype(str)),
    "date": pd.to_datetime(prospective["Date"]).dt.strftime("%Y-%m-%d"),
    "home": prospective.get("HomeTeam", ""),
    "away": prospective.get("AwayTeam", ""),
    "prob_home": probs,
    "pred_label": preds,
    "odds_B365H": prospective.get("B365H", np.nan),
    "actual": prospective.get("HomeWin", np.nan),
})
out["model_source"] = model_path.name
out["snapshot_created_at"] = datetime.now(timezone.utc).isoformat()

ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT_PATH = OUT_DIR / f"predictions_snapshot_{ts}.csv"
out.to_csv(OUT_PATH, index=False)
print("Saved snapshot:", OUT_PATH)
print(out.head().to_dict(orient='records'))


# In[9]:


# Load model, prepare X_eval, predict and save snapshot (run after you confirmed feature_list loaded)
import joblib, pandas as pd, numpy as np
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone

MODELS_DIR = Path.cwd().joinpath("../../models/thirdIterration/boost").resolve()

# pick model (prefer LightGBM)
model_path = lgb if 'lgb' in globals() and lgb is not None else (xgb if 'xgb' in globals() and xgb is not None else None)
if model_path is None:
    model_path = next(MODELS_DIR.glob("*lightgbm*.pkl"), None) or next(MODELS_DIR.glob("*xgboost*.pkl"), None)
assert model_path is not None, f"No model file found in {MODELS_DIR}"

# load into variable `model`
model = joblib.load(model_path)
print("Loaded model:", model_path.name)

# require feature_list
assert feature_list is not None, "feature_list variable not loaded. Run your feature_list load cell."

# infer train_end_date and pick prospective rows
train_end_date = pd.to_datetime(train_df_clean['Date']).max()
print("train_end_date:", train_end_date)
prospective = eval_df_clean[pd.to_datetime(eval_df_clean['Date']) > train_end_date].reset_index(drop=True)
print("Prospective rows:", prospective.shape[0])
if prospective.shape[0] == 0:
    raise RuntimeError("No prospective rows found. Check Date parsing and train_end_date.")

# prepare X_eval and normalize column names safely (avoid collisions)
def safe_colname(c):
    return (c.replace('>', '_gt_')
             .replace('<', '_lt_')
             .replace('[', '_')
             .replace(']', '_')
             .replace('/', '_')
             .replace(' ', '_')
             .replace('%', 'pct')
             .replace('.', '_')
             )
X_eval = prospective.drop(columns=cols_to_drop, errors='ignore').copy()
X_eval.columns = [safe_colname(c) for c in X_eval.columns]
X_eval = X_eval.apply(pd.to_numeric, errors='coerce')

# merge duplicate columns (transpose-groupby, avoids future warning)
dup = X_eval.columns[X_eval.columns.duplicated()].unique()
if len(dup):
    print("Merging duplicate columns:", list(dup))
    X_eval = X_eval.T.groupby(level=0).mean().T
    print("After merge X_eval shape:", X_eval.shape)

# dedupe feature_list while preserving order (if necessary)
feat_counts = Counter(feature_list)
if any(v > 1 for v in feat_counts.values()):
    seen = set(); new_feat = []
    for f in feature_list:
        if f not in seen:
            seen.add(f); new_feat.append(f)
    feature_list = new_feat
    print("Deduplicated feature_list length:", len(feature_list))

# align columns to feature_list, filling missing with 0
missing_feats = [f for f in feature_list if f not in X_eval.columns]
if missing_feats:
    print(f"Filling {len(missing_feats)} missing features with 0. Examples:", missing_feats[:10])
X_eval = X_eval.reindex(columns=feature_list, fill_value=0).fillna(0)

# predict probabilities
if hasattr(model, "predict_proba"):
    probs = model.predict_proba(X_eval.values)[:, 1]
else:
    preds_tmp = model.predict(X_eval.values)
    probs = preds_tmp.astype(float)

preds = (probs >= 0.5).astype(int)
print("Predicted probabilities for", len(probs), "rows.")

# build and save snapshot
OUT_DIR = Path.cwd() / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)
ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
out = pd.DataFrame({
    "match_id": prospective.get("match_id", prospective.index.astype(str)),
    "date": pd.to_datetime(prospective["Date"]).dt.strftime("%Y-%m-%d"),
    "home": prospective.get("HomeTeam", ""),
    "away": prospective.get("AwayTeam", ""),
    "prob_home": probs,
    "pred_label": preds,
    "odds_B365H": prospective.get("B365H", np.nan),
    "actual": prospective.get("HomeWin", np.nan),
})
out["model_source"] = model_path.name
out["snapshot_created_at"] = datetime.now(timezone.utc).isoformat()
out_path = OUT_DIR / f"predictions_snapshot_{ts}.csv"
out.to_csv(out_path, index=False)
print("Saved snapshot:", out_path)
print(out.head().to_dict(orient='records'))


# In[ ]:




