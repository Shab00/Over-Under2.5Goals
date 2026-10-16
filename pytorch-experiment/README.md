# PyTorch vs LightGBM: Football Match Outcome Prediction

Isolated experiment comparing PyTorch neural network against LightGBM baseline for predicting home wins in football matches.

## Structure

```
pytorch-experiment/
├── src/
│   ├── dataset.py           # FootballDataset class, time-based split
│   ├── model.py             # HomeWinNet (3-layer MLP)
│   ├── train.py             # PyTorch training with MLflow logging
│   ├── train_lgbm_baseline.py # LightGBM baseline on same split
│   └── compare.py           # Model comparison & metrics
├── artifacts/               # Outputs: loss curves, calibration plots, comparison table
├── mlruns/                  # MLflow runs (local)
├── requirements.txt         # Dependencies
└── README.md
```

## Data

- **Source**: `../data/processed/engineered_train_features.csv` (9,679 rows, 244 columns)
- **Features**: 218 selected features (from `../models/weekly/homewin/feature_list_*.pkl`)
- **Target**: `FTR == 'H'` → Home Win (1), else (0)
- **Date Range**: 2000-08-26 to 2026-09-20
- **Split**: Time-based 70% train / 15% val / 15% test

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Train PyTorch model
python src/train.py

# Train LightGBM baseline
python src/train_lgbm_baseline.py

# Compare results
python src/compare.py
```

## Model Architectures

### PyTorch (HomeWinNet)

- Input: 218 features
- Layer 1: Linear(218, 128) → BatchNorm → ReLU → Dropout(0.3)
- Layer 2: Linear(128, 64) → BatchNorm → ReLU → Dropout(0.3)
- Layer 3: Linear(64, 1) → BCEWithLogitsLoss

**Training**:
- Optimizer: Adam (lr=1e-3)
- Scheduler: ReduceLROnPlateau (patience=5, factor=0.5)
- Early Stopping: patience=10 on validation loss
- Batch Size: 64
- Max Epochs: 100

### LightGBM Baseline

- n_estimators: 100
- learning_rate: 0.1
- num_leaves: 31
- Early Stopping: patience=10 on validation set

## Outputs

### MLflow

Local MLflow tracking at `./mlruns` with experiment `pytorch_vs_lightgbm`:
- **pytorch_homewin**: PyTorch model run
- **lightgbm_baseline**: LightGBM baseline run

Each run logs:
- Hyperparameters
- Per-epoch metrics (train_loss, val_loss)
- Test metrics (ROC-AUC, Accuracy, Log-Loss, Brier Score)
- Saved models

### Artifacts

- `artifacts/loss_curve.png`: PyTorch training curve (train vs val loss)
- `artifacts/calibration_comparison.png`: Reliability diagrams (both models)
- `artifacts/comparison.csv`: Metrics summary table

## Metrics

Evaluated on the held-out test set (last 15% by date):

| Metric | Description |
|--------|-------------|
| **ROC-AUC** | Area under receiver-operating characteristic curve (0-1, higher better) |
| **Accuracy** | Proportion correct (threshold 0.5) |
| **Log-Loss** | Cross-entropy loss (lower better) |
| **Brier Score** | Mean squared error of probabilities (lower better) |

## Notes

- Data handling: NaN values replaced with 0 (equivalent to LightGBM's `nan_to_num`)
- Time-based split preserves temporal order (no data leakage)
- Models use **identical feature sets** for fair apples-to-apples comparison
- MLflow runs are isolated locally; not logged to DagsHub (clean separation for review)
- This is a **proof-of-concept only**; not integrated into the live pipeline
