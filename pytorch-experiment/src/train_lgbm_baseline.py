import sys
from pathlib import Path
import pickle
import joblib

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, accuracy_score, log_loss, brier_score_loss
import lightgbm as lgb
import mlflow
import mlflow.lightgbm

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))
from dataset import FootballDataset, get_time_based_split


def main():
    # Paths
    data_dir = Path(__file__).parent.parent.parent / "data" / "processed"
    models_dir = Path(__file__).parent.parent.parent / "models" / "weekly" / "homewin"
    csv_path = data_dir / "engineered_train_features.csv"
    feature_list_path = sorted(models_dir.glob("feature_list_*.pkl"))[-1]  # latest
    artifacts_dir = Path(__file__).parent.parent / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    print(f"[train_lgbm] Loading data from {csv_path}")
    print(f"[train_lgbm] Using features from {feature_list_path}")

    # Time-based split
    (
        train_idx,
        val_idx,
        test_idx,
        train_min,
        train_max,
        val_min,
        val_max,
        test_min,
        test_max,
    ) = get_time_based_split(str(csv_path), train_ratio=0.70, val_ratio=0.15)
    print(f"[train_lgbm] Train: {len(train_idx)} samples ({train_min.date()} - {train_max.date()})")
    print(f"[train_lgbm] Val: {len(val_idx)} samples ({val_min.date()} - {val_max.date()})")
    print(f"[train_lgbm] Test: {len(test_idx)} samples ({test_min.date()} - {test_max.date()})")

    # Create datasets
    train_dataset = FootballDataset(str(csv_path), str(feature_list_path), train_idx)
    val_dataset = FootballDataset(str(csv_path), str(feature_list_path), val_idx)
    test_dataset = FootballDataset(str(csv_path), str(feature_list_path), test_idx)

    X_train, y_train = train_dataset.X, train_dataset.y
    X_val, y_val = val_dataset.X, val_dataset.y
    X_test, y_test = test_dataset.X, test_dataset.y

    print(f"[train_lgbm] X_train shape: {X_train.shape}, y_train shape: {y_train.shape}")

    # Train LightGBM with default-ish hyperparameters (similar to jobs/train_model.py)
    model = lgb.LGBMClassifier(
        random_state=42,
        n_estimators=100,
        learning_rate=0.1,
        num_leaves=31,
        max_depth=-1,
        verbose=-1,
    )

    print("[train_lgbm] Training LightGBM...")
    model.fit(
        X_train,
        y_train,
        eval_set=[(X_val, y_val)],
        callbacks=[lgb.early_stopping(10), lgb.log_evaluation(period=0)],
    )

    # Evaluate on test set
    test_probs = model.predict_proba(X_test)[:, 1]
    test_pred = model.predict(X_test)
    test_auc = roc_auc_score(y_test, test_probs)
    test_acc = accuracy_score(y_test, test_pred)
    test_logloss = log_loss(y_test, test_probs)
    test_brier = brier_score_loss(y_test, test_probs)

    print(f"\n[train_lgbm] Test metrics:")
    print(f"  ROC-AUC: {test_auc:.4f}")
    print(f"  Accuracy: {test_acc:.4f}")
    print(f"  Log-Loss: {test_logloss:.4f}")
    print(f"  Brier Score: {test_brier:.4f}")

    # Save local copy for compare.py
    local_model_path = artifacts_dir / "lgbm_model.pkl"
    joblib.dump(model, local_model_path)
    print(f"[train_lgbm] Saved LightGBM model to {local_model_path}")

    # MLflow setup
    mlflow.set_tracking_uri("sqlite:///mlflow.db")
    mlflow.set_experiment("pytorch_vs_lightgbm")

    with mlflow.start_run(run_name="lightgbm_baseline"):
        # Log hyperparameters
        mlflow.log_param("model", "LGBMClassifier")
        mlflow.log_param("n_estimators", 100)
        mlflow.log_param("learning_rate", 0.1)
        mlflow.log_param("num_leaves", 31)
        mlflow.log_param("random_state", 42)
        mlflow.log_param("train_size", len(train_dataset))
        mlflow.log_param("val_size", len(val_dataset))
        mlflow.log_param("test_size", len(test_dataset))

        # Log metrics
        mlflow.log_metric("test_roc_auc", test_auc)
        mlflow.log_metric("test_accuracy", test_acc)
        mlflow.log_metric("test_logloss", test_logloss)
        mlflow.log_metric("test_brier_score", test_brier)

        # Log model to MLflow (best-effort)
        try:
            mlflow.lightgbm.log_model(model, "model")
        except Exception as e:
            print(f"[train_lgbm] MLflow model logging skipped: {e}")

    print(f"[train_lgbm] MLflow run saved to ./mlflow.db")


if __name__ == "__main__":
    main()
