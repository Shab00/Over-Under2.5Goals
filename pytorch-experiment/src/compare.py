"""
Compare PyTorch and LightGBM predictions.
Reads predictions.csv produced by export_predictions.py — no model loading
here, so no OpenMP conflict.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, accuracy_score, log_loss, brier_score_loss
import matplotlib.pyplot as plt

artifacts_dir = Path(__file__).parent.parent / "artifacts"


def get_calibration_curve(y_true, y_pred, n_bins=10):
    bin_sums = np.zeros(n_bins)
    bin_true = np.zeros(n_bins)
    bin_total = np.zeros(n_bins)
    bin_edges = np.linspace(0, 1, n_bins + 1)
    for i in range(n_bins):
        mask = (y_pred >= bin_edges[i]) & (y_pred < bin_edges[i + 1])
        if i == n_bins - 1:
            mask = (y_pred >= bin_edges[i]) & (y_pred <= bin_edges[i + 1])
        bin_sums[i] = np.sum(y_pred[mask])
        bin_true[i] = np.sum(y_true[mask])
        bin_total[i] = np.sum(mask)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    bin_true_frac = np.divide(bin_true, bin_total, where=bin_total > 0, out=np.zeros_like(bin_true))
    bin_pred_frac = np.divide(bin_sums, bin_total, where=bin_total > 0, out=np.zeros_like(bin_sums))
    return bin_centers, bin_pred_frac, bin_true_frac


def plot_calibration_comparison(y_test, pytorch_probs, lgbm_probs, save_path):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    _, pyt_pred, pyt_true = get_calibration_curve(y_test, pytorch_probs, n_bins=10)
    axes[0].plot([0, 1], [0, 1], "k--", label="Perfectly calibrated")
    axes[0].plot(pyt_pred, pyt_true, "o-", label="PyTorch", markersize=6)
    axes[0].set_xlabel("Mean Predicted Probability")
    axes[0].set_ylabel("Fraction of Positives")
    axes[0].set_title("PyTorch Calibration")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    axes[0].set_xlim([0, 1])
    axes[0].set_ylim([0, 1])

    _, lgbm_pred, lgbm_true = get_calibration_curve(y_test, lgbm_probs, n_bins=10)
    axes[1].plot([0, 1], [0, 1], "k--", label="Perfectly calibrated")
    axes[1].plot(lgbm_pred, lgbm_true, "s-", label="LightGBM", markersize=6, color="orange")
    axes[1].set_xlabel("Mean Predicted Probability")
    axes[1].set_ylabel("Fraction of Positives")
    axes[1].set_title("LightGBM Calibration")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)
    axes[1].set_xlim([0, 1])
    axes[1].set_ylim([0, 1])

    plt.tight_layout()
    plt.savefig(save_path, dpi=100, bbox_inches="tight")
    plt.close()


def main():
    csv_path = artifacts_dir / "predictions.csv"
    if not csv_path.exists():
        print(f"[compare] {csv_path} not found. Run `python src/export_predictions.py` first.")
        return

    df = pd.read_csv(csv_path)
    y_test = df["y_test"].values
    pytorch_probs = df["pytorch_probs"].values
    lgbm_probs = df["lgbm_probs"].values

    print(f"[compare] Loaded {len(y_test)} predictions")

    # Compute metrics
    pytorch_auc = roc_auc_score(y_test, pytorch_probs)
    pytorch_acc = accuracy_score(y_test, (pytorch_probs > 0.5).astype(int))
    pytorch_logloss = log_loss(y_test, pytorch_probs)
    pytorch_brier = brier_score_loss(y_test, pytorch_probs)

    lgbm_auc = roc_auc_score(y_test, lgbm_probs)
    lgbm_acc = accuracy_score(y_test, (lgbm_probs > 0.5).astype(int))
    lgbm_logloss = log_loss(y_test, lgbm_probs)
    lgbm_brier = brier_score_loss(y_test, lgbm_probs)

    # Print comparison
    print("\n" + "=" * 80)
    print("COMPARISON TABLE: PyTorch vs LightGBM")
    print("=" * 80)
    print(f"{'Metric':<20} {'PyTorch':<20} {'LightGBM':<20} {'Winner':<20}")
    print("-" * 80)

    def compare_metric(name, pyt_val, lgbm_val, higher_is_better=True):
        winner = "PyTorch" if (pyt_val > lgbm_val) == higher_is_better else "LightGBM"
        print(f"{name:<20} {pyt_val:<20.4f} {lgbm_val:<20.4f} {winner:<20}")

    compare_metric("ROC-AUC", pytorch_auc, lgbm_auc, higher_is_better=True)
    compare_metric("Accuracy", pytorch_acc, lgbm_acc, higher_is_better=True)
    compare_metric("Log-Loss", pytorch_logloss, lgbm_logloss, higher_is_better=False)
    compare_metric("Brier Score", pytorch_brier, lgbm_brier, higher_is_better=False)
    print("=" * 80)

    comparison_data = {
        "Model": ["PyTorch", "LightGBM"],
        "ROC-AUC": [pytorch_auc, lgbm_auc],
        "Accuracy": [pytorch_acc, lgbm_acc],
        "Log-Loss": [pytorch_logloss, lgbm_logloss],
        "Brier Score": [pytorch_brier, lgbm_brier],
    }
    comparison_df = pd.DataFrame(comparison_data)
    comparison_csv = artifacts_dir / "comparison.csv"
    comparison_df.to_csv(comparison_csv, index=False)
    print(f"\n[compare] Saved comparison to {comparison_csv}")

    calibration_path = artifacts_dir / "calibration_comparison.png"
    plot_calibration_comparison(y_test, pytorch_probs, lgbm_probs, calibration_path)
    print(f"[compare] Saved calibration plot to {calibration_path}")


if __name__ == "__main__":
    main()
