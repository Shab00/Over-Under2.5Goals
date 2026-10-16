import pickle
import re
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import torch
from torch.utils.data import Dataset


# Try to import sanitize_feature_names from the main pipeline.
# Fall back to an inline copy if the import fails (e.g. when run from
# a different directory or if jobs/ isn't on sys.path).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_JOBS_DIR = _REPO_ROOT / "jobs"
if _JOBS_DIR.exists():
    sys.path.insert(0, str(_JOBS_DIR))

try:
    from train_model import sanitize_feature_names  # type: ignore
except ImportError:
    def sanitize_feature_names(cols):
        """Inline fallback — must match jobs/train_model.py exactly."""
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


class FootballDataset(Dataset):
    """
    Loads engineered training features and creates PyTorch dataset.
    Uses the same 218 features as the LightGBM model.
    Target: FTR == 'H' (home win) → 1, else 0.
    Handles NaN → 0 (LightGBM's nan_to_num equivalent).
    """

    def __init__(
        self,
        csv_path: str,
        feature_list_path: str,
        indices: np.ndarray = None,
    ):
        """
        Args:
            csv_path: Path to engineered_train_features.csv
            feature_list_path: Path to feature_list_*.pkl from LightGBM model
            indices: Row indices to use (train/val/test split). If None, use all.
        """
        self.df = pd.read_csv(csv_path, low_memory=False)
        self.df["Date"] = pd.to_datetime(self.df["Date"])

        # CRITICAL: sort by date so row indices from get_time_based_split()
        # (which sorts the same way) line up correctly. Without this, the
        # "time-based" split silently becomes random.
        self.df = self.df.sort_values("Date").reset_index(drop=True)

        # Sanitize column names to match the feature_list, which is already
        # in sanitized form (e.g. "HomeTeam_Man_City", "B365_gt_2_5").
        self.df.columns = sanitize_feature_names(list(self.df.columns))

        with open(feature_list_path, "rb") as f:
            self.feature_names = pickle.load(f)

        if indices is not None:
            self.df = self.df.iloc[indices].reset_index(drop=True)

        # Extract features and target
        self.X = self.df[self.feature_names].values.astype(np.float32)
        # Replace NaN with 0
        self.X = np.nan_to_num(self.X, nan=0.0)
        # Target: HomeWin == 1, else 0
        self.y = (self.df["FTR"] == "H").astype(np.float32).values

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx: int):
        x = torch.from_numpy(self.X[idx]).float()
        y = torch.tensor(self.y[idx], dtype=torch.float32)
        return x, y


def get_time_based_split(csv_path: str, train_ratio: float = 0.70, val_ratio: float = 0.15):
    """
    Time-based split: sort by date, split into train/val/test.
    Returns indices for each split.
    """
    df = pd.read_csv(csv_path, low_memory=False)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    n = len(df)
    train_end = int(n * train_ratio)
    val_end = int(n * (train_ratio + val_ratio))

    train_indices = np.arange(0, train_end)
    val_indices = np.arange(train_end, val_end)
    test_indices = np.arange(val_end, n)

    train_dates = df.iloc[train_indices]["Date"]
    val_dates = df.iloc[val_indices]["Date"]
    test_dates = df.iloc[test_indices]["Date"]

    return (
        train_indices,
        val_indices,
        test_indices,
        train_dates.min(),
        train_dates.max(),
        val_dates.min(),
        val_dates.max(),
        test_dates.min(),
        test_dates.max(),
    )
