import sys, re, pickle
from pathlib import Path
import joblib
import numpy as np
import pandas as pd

data_dir = Path(__file__).parent.parent.parent / "data" / "processed"
models_dir = Path(__file__).parent.parent.parent / "models" / "weekly" / "homewin"
artifacts_dir = Path(__file__).parent.parent / "artifacts"
csv_path = data_dir / "engineered_train_features.csv"
feature_list_path = sorted(models_dir.glob("feature_list_*.pkl"))[-1]

def sanitize(cols):
    out, seen = [], {}
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

print("[lgbm] Loading CSV...")
df = pd.read_csv(csv_path, low_memory=False)
df["Date"] = pd.to_datetime(df["Date"])
df = df.sort_values("Date").reset_index(drop=True)
df.columns = sanitize(list(df.columns))

with open(feature_list_path, "rb") as f:
    feature_list = pickle.load(f)

n = len(df)
test_df = df.iloc[int(n * 0.85):].reset_index(drop=True)
X_test = np.nan_to_num(test_df[feature_list].values.astype(np.float32), nan=0.0)
print(f"[lgbm] Test set: {len(X_test)} samples")

print("[lgbm] Loading model...")
model = joblib.load(artifacts_dir / "lgbm_model.pkl")

print("[lgbm] Predicting...")
probs = model.predict_proba(X_test)[:, 1]

pt = pd.read_csv(artifacts_dir / "predictions_pytorch.csv")
pt["lgbm_probs"] = probs
pt.to_csv(artifacts_dir / "predictions.csv", index=False)
print(f"[lgbm] Saved {artifacts_dir / 'predictions.csv'}")
