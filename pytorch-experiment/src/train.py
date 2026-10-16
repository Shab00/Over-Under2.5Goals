import os
import sys
from pathlib import Path
import pickle
from datetime import datetime

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
import mlflow
import mlflow.pytorch
from sklearn.metrics import roc_auc_score, accuracy_score, log_loss, brier_score_loss
import matplotlib.pyplot as plt

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))
from dataset import FootballDataset, get_time_based_split
from model import HomeWinNet


def train_epoch(model, train_loader, criterion, optimizer, device):
    """Train one epoch."""
    model.train()
    total_loss = 0.0
    for X, y in train_loader:
        X, y = X.to(device), y.to(device)
        optimizer.zero_grad()
        logits = model(X).squeeze()
        loss = criterion(logits, y)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * len(y)
    return total_loss / len(train_loader.dataset)


def eval_epoch(model, val_loader, criterion, device):
    """Evaluate on validation set."""
    model.eval()
    total_loss = 0.0
    with torch.no_grad():
        for X, y in val_loader:
            X, y = X.to(device), y.to(device)
            logits = model(X).squeeze()
            loss = criterion(logits, y)
            total_loss += loss.item() * len(y)
    return total_loss / len(val_loader.dataset)


def get_predictions(model, dataloader, device):
    """Get predictions and labels."""
    model.eval()
    all_logits = []
    all_labels = []
    with torch.no_grad():
        for X, y in dataloader:
            X = X.to(device)
            logits = model(X).squeeze()
            all_logits.append(logits.cpu().numpy())
            all_labels.append(y.numpy())
    logits = np.concatenate(all_logits)
    labels = np.concatenate(all_labels)
    probs = 1 / (1 + np.exp(-logits))  # sigmoid
    return probs, labels


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[train] Using device: {device}")

    # Paths
    data_dir = Path(__file__).parent.parent.parent / "data" / "processed"
    models_dir = Path(__file__).parent.parent.parent / "models" / "weekly" / "homewin"
    csv_path = data_dir / "engineered_train_features.csv"
    feature_list_path = sorted(models_dir.glob("feature_list_*.pkl"))[-1]  # latest
    artifacts_dir = Path(__file__).parent.parent / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    print(f"[train] Loading data from {csv_path}")
    print(f"[train] Using features from {feature_list_path}")

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
    print(f"[train] Train: {len(train_idx)} samples ({train_min.date()} - {train_max.date()})")
    print(f"[train] Val: {len(val_idx)} samples ({val_min.date()} - {val_max.date()})")
    print(f"[train] Test: {len(test_idx)} samples ({test_min.date()} - {test_max.date()})")

    # Create datasets and loaders
    train_dataset = FootballDataset(str(csv_path), str(feature_list_path), train_idx)
    val_dataset = FootballDataset(str(csv_path), str(feature_list_path), val_idx)
    test_dataset = FootballDataset(str(csv_path), str(feature_list_path), test_idx)

    batch_size = 64
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)

    # Model, loss, optimizer
    input_size = len(train_dataset.feature_names)
    dropout_rate = 0.3
    learning_rate = 1e-3
    model = HomeWinNet(input_size=input_size, dropout=dropout_rate).to(device)
    criterion = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=5
    )

    # Training params
    max_epochs = 100
    early_stopping_patience = 10
    best_val_loss = float("inf")
    epochs_without_improvement = 0
    best_model_state = None

    # MLflow setup
    mlflow.set_tracking_uri("sqlite:///mlflow.db")
    mlflow.set_experiment("pytorch_vs_lightgbm")

    with mlflow.start_run(run_name="pytorch_homewin"):
        # Log hyperparameters
        mlflow.log_param("optimizer", "Adam")
        mlflow.log_param("learning_rate", learning_rate)
        mlflow.log_param("batch_size", batch_size)
        mlflow.log_param("dropout", dropout_rate)
        mlflow.log_param("hidden_sizes", [128, 64])
        mlflow.log_param("max_epochs", max_epochs)
        mlflow.log_param("early_stopping_patience", early_stopping_patience)
        mlflow.log_param("scheduler", "ReduceLROnPlateau")
        mlflow.log_param("train_size", len(train_dataset))
        mlflow.log_param("val_size", len(val_dataset))
        mlflow.log_param("test_size", len(test_dataset))

        # Training loop
        train_losses = []
        val_losses = []

        for epoch in range(max_epochs):
            train_loss = train_epoch(model, train_loader, criterion, optimizer, device)
            val_loss = eval_epoch(model, val_loader, criterion, device)
            train_losses.append(train_loss)
            val_losses.append(val_loss)

            scheduler.step(val_loss)

            if (epoch + 1) % 10 == 0:
                print(f"Epoch {epoch+1}/{max_epochs} | train_loss={train_loss:.4f} | val_loss={val_loss:.4f}")

            mlflow.log_metric("train_loss", train_loss, step=epoch)
            mlflow.log_metric("val_loss", val_loss, step=epoch)

            # Early stopping
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                epochs_without_improvement = 0
                best_model_state = model.state_dict().copy()
            else:
                epochs_without_improvement += 1
                if epochs_without_improvement >= early_stopping_patience:
                    print(f"[train] Early stopping at epoch {epoch+1}")
                    break

        # Restore best model
        if best_model_state is not None:
            model.load_state_dict(best_model_state)
        epochs_trained = epoch + 1

        # Evaluate on test set
        test_probs, test_labels = get_predictions(model, test_loader, device)
        test_auc = roc_auc_score(test_labels, test_probs)
        test_acc = accuracy_score(test_labels, (test_probs > 0.5).astype(int))
        test_logloss = log_loss(test_labels, test_probs)
        test_brier = brier_score_loss(test_labels, test_probs)

        print(f"\n[train] Test metrics:")
        print(f"  ROC-AUC: {test_auc:.4f}")
        print(f"  Accuracy: {test_acc:.4f}")
        print(f"  Log-Loss: {test_logloss:.4f}")
        print(f"  Brier Score: {test_brier:.4f}")

        mlflow.log_metric("test_roc_auc", test_auc)
        mlflow.log_metric("test_accuracy", test_acc)
        mlflow.log_metric("test_logloss", test_logloss)
        mlflow.log_metric("test_brier_score", test_brier)
        mlflow.log_param("epochs_trained", epochs_trained)

        # Save local copy for compare.py
        model.eval()
        local_model_path = artifacts_dir / "pytorch_model.pt"
        torch.save(model.state_dict(), local_model_path)
        print(f"[train] Saved PyTorch model to {local_model_path}")

        # Also log to MLflow (best-effort; some MLflow 3.x setups reject artifacts)
        try:
            input_example = np.zeros((1, input_size), dtype=np.float32)
            mlflow.pytorch.log_model(
                model,
                "model",
                input_example=input_example,
                serialization_format="pickle",
            )
        except Exception as e:
            print(f"[train] MLflow model logging skipped: {e}")

        # Save training curve
        plt.figure(figsize=(10, 6))
        plt.plot(train_losses, label="Train Loss", marker="o", markersize=3)
        plt.plot(val_losses, label="Val Loss", marker="s", markersize=3)
        plt.xlabel("Epoch")
        plt.ylabel("Loss")
        plt.title("PyTorch Training Curve")
        plt.legend()
        plt.grid(True, alpha=0.3)
        curve_path = artifacts_dir / "loss_curve.png"
        plt.savefig(curve_path, dpi=100, bbox_inches="tight")
        plt.close()
        mlflow.log_artifact(str(curve_path))
        print(f"[train] Saved loss curve to {curve_path}")

    print(f"[train] MLflow run saved to ./mlflow.db")


if __name__ == "__main__":
    main()
