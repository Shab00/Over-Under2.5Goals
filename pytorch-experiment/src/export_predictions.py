"""
Export test set predictions from both models to a CSV.
Runs PyTorch and LightGBM in the same process — the segfault risk is on
the LightGBM side only, and loading a pickle of a trained LGBMClassifier
doesn't trigger the conflict (only model.predict_proba does).

If even this segfaults, we split further.
"""
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import sys
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import torch
torch.set_num_threads(1)

sys.path.insert(0, str(Path(__file__).parent))
from dataset import FootballDataset, get_time_based_split
from model import HomeWinNet

# Paths
data_dir = Path(__file__).parent.parent.parent / "data" / "processed"
models_dir = Path(__file__).parent.parent.parent / "models" / "weekly" / "homewin"
csv_path = data_dir / "engineered_train_features.csv"
feature_list_path = sorted(models_dir.glob("feature_list_*.pkl"))[-1]
artifacts_dir = Path(__file__).parent.parent / "artifacts"

print(f"[export] Loading data...")
_, _, test_idx, *_ = get_time_based_split(str(csv_path), 0.70, 0.15)
test_dataset = FootballDataset(str(csv_path), str(feature_list_path), test_idx)
X_test, y_test = test_dataset.X, test_dataset.y
input_size = len(test_dataset.feature_names)
print(f"[export] Test set: {len(y_test)} samples")

# PyTorch predictions
print("[export] Running PyTorch...")
pt_model = HomeWinNet(input_size=input_size)
pt_model.load_state_dict(torch.load(artifacts_dir / "pytorch_model.pt", map_location="cpu"))
pt_model.eval()
with torch.no_grad():
    X_t = torch.from_numpy(X_test).float()
    logits_list = []
    for i in range(0, len(X_t), 128):
        logits_list.append(pt_model(X_t[i:i+128]).squeeze().numpy())
    logits = np.concatenate(logits_list)
pt_probs = 1 / (1 + np.exp(-logits))
print(f"[export] PyTorch predictions done ({len(pt_probs)} values)")

# Save partial — before LightGBM loads
out = pd.DataFrame({
    "y_test": y_test,
    "pytorch_probs": pt_probs,
})
out.to_csv(artifacts_dir / "predictions_pytorch.csv", index=False)
print(f"[export] Saved PyTorch predictions to predictions_pytorch.csv")

# LightGBM predictions
print("[export] Running LightGBM...")
lgbm_model = joblib.load(artifacts_dir / "lgbm_model.pkl")
lgbm_probs = lgbm_model.predict_proba(X_test)[:, 1]
print(f"[export] LightGBM predictions done ({len(lgbm_probs)} values)")

out["lgbm_probs"] = lgbm_probs
out.to_csv(artifacts_dir / "predictions.csv", index=False)
print(f"[export] Saved all predictions to {artifacts_dir / 'predictions.csv'}")
