# ⚽ Football Match Outcome Predictor

> End-to-end ML pipeline for predicting Premier League **HomeWin** outcomes — featuring automated fixture scraping, live bookmaker odds ingestion, LightGBM modelling, a FastAPI snapshot endpoint, and Telegram delivery.

[![CI](https://github.com/Shab00/Over-Under2.5Goals/actions/workflows/ci.yml/badge.svg)](https://github.com/Shab00/Over-Under2.5Goals/actions)

---

## Table of Contents

1. [Overview](#overview)
2. [How the Pipeline Works](#how-the-pipeline-works)
3. [Quick Start](#quick-start)
4. [Project Structure](#project-structure)
5. [Features](#features)
6. [Running Locally](#running-locally)
7. [API](#api)
8. [Monitoring & Observability](#monitoring--observability)
9. [Results & Evaluation](#results--evaluation)
10. [Changelog](#changelog)
11. [Next Steps](#next-steps)
12. [Acknowledgements](#acknowledgements)

---

## Overview

This project uses data analysis and machine learning to predict football match outcomes, with a primary focus on **HomeWin** (does the home team win?). It covers the full lifecycle:

- Raw data ingestion and cleaning
- Feature engineering (market odds, rolling form, team encoding)
- LightGBM model training with versioned artefacts
- A FastAPI snapshot endpoint serving calibrated probabilities
- A Telegram digest pipeline for automated pick delivery
- End-to-end observability via Prometheus + Grafana

**Target variable:** HomeWin  
**Key goal:** Push predictive accuracy toward 70% and demonstrate real-world value through betting simulation.

---

## How the Pipeline Works

```
Fixtures + Odds Scrape
        ↓
Canonicalisation & Feature Engineering
        ↓
LightGBM HomeWin Model (versioned artefacts)
        ↓
Snapshot CSV  →  FastAPI endpoint  →  Telegram digest
                                           ↓
                                    deliveries.db (logged)
```

**Step by step:**

1. **Scrape fixtures & odds** — Pulls upcoming EPL fixtures and merges live bookmaker odds (Bet365, Pinnacle, William Hill, 1XBet, and aggregators).
2. **Canonicalise & engineer features** — Standardises team names; computes rolling stats (recent goals, form) and odds-derived features.
3. **Odds mapping** — Home/draw/away and over/under markets are filled using best-available prices with fallback logic.
4. **Train & snapshot** — A versioned LightGBM model generates reproducible predictions saved to CSV. Model, feature list, and metadata are all artefacted.
5. **Serve & deliver** — FastAPI serves the latest snapshot; a Telegram digest script fetches picks, sends them, and logs every delivery to `deliveries.db`.

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Prepare data

Raw CSVs live in `data/raw/csvFiles/`. Run the cleaning/feature notebook or script:

```bash
# Option A — notebook
# Open notebooks/secondIterrationOdds/cleaningWithOdds-evaluation.ipynb and run all cells

# Option B — scripts (if available)
python3 jobs/scrape_matches.py --in-place
python3 jobs/train_homewin_weekly.py
```

Expected outputs:
- `data/processed/cleaned_data.csv`
- `data/processed/combinedWithOdds.csv`
- `data/processed/final_football_model_data.csv`
- `data/processed/fixtures_next7d.csv`

### 3. Run the weekly pipeline

```bash
make weekly   # or run the two jobs manually:
python3 jobs/scrape_matches.py --in-place
python3 jobs/train_homewin_weekly.py
```

### 4. Start the API

```bash
API_KEY="choose-a-secret" uvicorn src.api.main:APP --reload --port 8000
```

### 5. Send a Telegram digest

```bash
python scripts/deliver_telegram.py
```

---

## Project Structure

```
.
├── data/
│   ├── raw/csvFiles/          # Source CSVs
│   └── processed/             # Cleaned data, fixture snapshots, evaluation outputs
├── models/
│   └── weekly/homewin/        # Versioned LightGBM model, feature list, metadata
├── notebooks/
│   ├── firstIterration/       # Data cleaning & Random Forest baseline
│   ├── secondIterrationOdds/  # Odds-aware cleaning & business evaluation
│   └── thirdIterration/       # Boosting experiments & final pipeline
├── jobs/
│   ├── scrape_matches.py      # Fixture + odds scrape/upsert
│   └── train_homewin_weekly.py
├── src/api/                   # FastAPI app
├── scripts/
│   ├── send_telegram_digest.py
│   ├── smoke_test.sh
│   └── migrate_make_match_id_unique.sh
├── monitoring/
│   ├── grafana/dashboards/    # Importable Grafana JSON
│   └── webhook_receiver.py
├── tests/
│   └── test_idempotency.py
├── notes/                     # Feature audits and technical notes
├── DEVELOPER.md               # Local run recipes, observability, smoke tests
├── Makefile
└── docker-compose.yml
```

---

## Features

### Data Pipeline
- Ingestion, deduplication, and cleaning with canonical match keys
- Comprehensive feature engineering: market odds, team encoding, rolling form, contextual variables
- Idempotent scrape/upsert — safe to re-run without creating duplicates

### Modelling
- Classifiers tested: Random Forest, Gradient Boosting, Logistic Regression, MLP Neural Networks
- Final model: **LightGBM** (versioned artefacts: `.pkl` model, feature list, metadata JSON)
- Hyperparameter tuning and feature importance analysis
- Calibrated probabilities for downstream use

### Evaluation
- Robust cross-validation and threshold sweeps
- Business simulation: ROI, win rate, and PnL tracked via bookmaker odds
- Calibration curves and error analysis in notebooks

### Delivery & Logging
- FastAPI snapshot endpoint (`/predictions/latest`, `/predictions/info`)
- Telegram digest pipeline with idempotent `deliveries.db` logging
- Delivery metadata (threshold, prob_col) supports A/B testing and ROI tracking

---

## Running Locally

### Dev server

```bash
# Foreground
API_KEY="choose-a-secret" uvicorn src.api.main:APP --reload --port 8000

# Background
DELIVERIES_DB=/tmp/pytest_deliveries.db \
  python -m uvicorn src.api.main:APP --host 0.0.0.0 --port 8000 \
  &> uvicorn.log & echo $! > uvicorn.pid

# Or via Makefile
DELIVERIES_DB=/tmp/pytest_deliveries.db make dev
```

### Smoke tests

```bash
make smoke
# or
API_KEY="choose-a-secret" bash scripts/smoke_test.sh
```

### Tests

```bash
pytest
```

---

## API

| Endpoint | Method | Description |
|---|---|---|
| `/predictions/latest` | GET | Returns the latest snapshot predictions |
| `/predictions/info` | GET | Returns model metadata for the current snapshot |
| `/ingest` | POST | Ingest new rows (idempotent by `match_id`) |
| `/metrics` | GET | Prometheus metrics |

**Example ingest call:**

```bash
curl -X POST '<URL>/ingest' \
  -H 'Content-Type: application/json' \
  -H 'X-API-KEY: choose-a-secret' \
  -d '{"rows":[{"match_id":12345,"prob":0.5}],"source":"demo"}'
```

**Running with Docker:**

```bash
docker compose up -d
```

---

## Monitoring & Observability

Full local observability is configured via Docker Compose. See [`DEVELOPER.md`](DEVELOPER.md) for detailed recipes.

### Stack

| Tool | URL | Purpose |
|---|---|---|
| Prometheus | `http://localhost:9090` | Metrics scraping |
| Grafana | `http://localhost:3001` (admin/admin) | Dashboards |
| Alertmanager | — | Alert routing → webhook |

### Key metrics

- `smoke_test_runs_total{kind="api", result="success|error"}` — API smoke test counter
- `alertmanager_webhook_deliveries_total` — Alertmanager → webhook delivery counter

### Smoke test (end-to-end alerting)

```bash
chmod +x monitoring/ci/run_alertmanager_webhook_smoke.sh
monitoring/ci/run_alertmanager_webhook_smoke.sh

# Slower CI runners:
WAIT_SEC=30 monitoring/ci/run_alertmanager_webhook_smoke.sh
```

### Grafana dashboard

Import `monitoring/grafana/dashboards/smoke_dashboard.json` into Grafana. Panels show total smoke runs, runs over the last hour, and run rate.

---

## Results & Evaluation

- End-to-end flow validated: `fixture scrape → model training → snapshot → API → Telegram → deliveries.db`
- Calibration metrics, business simulation outputs, and PnL analysis are in `notebooks/` and `data/evaluation/`
- Delivery logs enable per-user ROI tracking and threshold A/B experiments

Where to find outputs:

| Artefact | Location |
|---|---|
| Trained models | `models/weekly/homewin/` |
| Processed data | `data/processed/` |
| Evaluation outputs | `data/evaluation/` |
| Reproducible analysis | `notebooks/` |
| Feature audits | `notes/` |

---

## Changelog

### April 2026 — Full Pipeline Automation
- Automated end-to-end scraping of EPL fixtures, odds ingestion, feature engineering, and HomeWin predictions for all upcoming matches
- All major bookmaker markets (Bet365, Pinnacle, etc.) mapped and populated

### March 2026 — Fixture & Odds Pipeline
- Built odds ingestion and merge scripts with fallback logic (Bet365 → Pinnacle → William Hill → aggregator)
- Pipeline filters for future, unplayed matches only
- Weekly orchestrator and Makefile targets for single-command operation

### March 2026 — Observability & Smoke Tests
- API smoke test validates `/ingest` HTTP 200, response shape, and idempotency
- Prometheus counter incremented on successful/failed ingest
- Grafana dashboard JSON added (importable)
- Alertmanager → webhook smoke test added to CI

### February 2026 — CI & Idempotency
- Added `test_idempotency.py` — integration test that posts the same `match_id` twice and asserts the second is skipped
- Added `.github/workflows/ci.yml` — GitHub Actions runs pytest on every push and PR
- `UNIQUE` index on `match_id` enforced at both application and DB level

### Earlier — Telegram Delivery & API
- Dockerised FastAPI snapshot endpoint serving calibrated probabilities
- Telegram digest pipeline with full delivery logging to `deliveries.db`

---

## Next Steps

- Use `deliveries.db` to run A/B tests on thresholds and message formats
- Add a lightweight admin UI for inspecting deliveries and re-sending picks
- Continue model calibration and explore live-data integration
- Extend models to other targets: over/under 2.5, away win, draw
- Keep [`DEVELOPER.md`](DEVELOPER.md) up to date with observability and run recipes

---

## Acknowledgements

This project is for educational and sports analytics purposes only. Data sourced from [Football-Data.co.uk](https://www.football-data.co.uk/) and other open football statistics archives.
