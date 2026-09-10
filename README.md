# ⚽ Football Match Outcome Predictor

End-to-end machine learning pipeline for predicting Premier League **HomeWin** outcomes.  
The system is fully automated and currently running for the **2026–27 season**.

[![CI](https://github.com/Shab00/Over-Under2.5Goals/actions/workflows/ci.yml/badge.svg)](https://github.com/Shab00/Over-Under2.5Goals/actions)

**Live predictions:** [https://shab00.github.io/football/](https://shab00.github.io/football/)  
**Telegram channel:** [https://t.me/HomeWinPrediction](https://t.me/HomeWinPrediction)

---

## Overview

This project predicts whether the home team will win an upcoming Premier League match. It covers the full machine learning lifecycle:

- Automated fixture and odds scraping (including Asian handicap)
- Feature engineering (rolling form, market odds, team encoding)
- LightGBM model training with versioned artefacts
- Calibrated probability outputs
- Live serving via GitHub Pages and Telegram
- Performance tracking (overall accuracy, value bets, profit)

**Target variable:** `HomeWin`  
**Key goal:** Identify value bets where the model's probability exceeds the bookmaker implied probability.

---

## AI Pundit Agent (RAG Layer)

The pipeline now includes a RAG-powered AI pundit agent that generates written betting strategy for every gameweek.

**How it works:**
- Live injury news scraped daily from NewsNow and accumulated in a compound knowledge base
- Past strategies archived with outcomes after each gameweek — the system learns from what worked
- FAISS vector store activates automatically after 20 scored strategies for embedding-based similarity retrieval
- GPT-4o-mini reasons over pre-computed context (form, H2H, value gaps) to produce per-fixture analysis with written justification

**Engineering decisions:**
- All maths pre-computed in Python — the LLM receives clean labelled facts, never raw numbers
- Pydantic v2 schema validation on every GPT output
- Graceful fallback to model signals if OpenAI is unavailable — pipeline never goes dark
- Delivered via Telegram and injected into the GitHub Pages predictions page on every training run

---

## How the Pipeline Works

```
Scrape fixtures + odds (football-data.co.uk, The-Odds-API)
↓
Standardise teams & engineer features (form, odds, Asian handicap)
↓
Train LightGBM model (versioned artefacts)
↓
Build prediction snapshot (CSV)
↓
Serve live page (GitHub Pages) & Deliver picks (Telegram)
↓
After matches: merge results → update performance tracker
```

Two automated workflows run on GitHub Actions:

1. **Weekly Pipeline** – runs 1 hour before each kick‑off slot.
   - Scrapes latest odds, trains model, generates predictions, sends Telegram message, archives snapshot, commits updates.

2. **Post Match Results Update** – runs daily at 07:00 UTC.
   - Updates historical results, merges with archived predictions, refreshes performance tracker, pushes changes.

The live page is automatically deployed after each successful workflow.

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set environment variables

Create a `.env` file or export these variables locally:

```bash
export ODDS_API_KEY="your-the-odds-api-key"
export TELEGRAM_BOT_TOKEN="your-telegram-bot-token"
export TELEGRAM_CHAT_ID="your-telegram-chat-id"
```

### 3. Run the full pipeline locally

```bash
bash jobs/run_weekly_pipeline.sh
```

This will:

- Scrape fixtures and odds
- Train the model
- Build features and predictions
- Send Telegram digest
- Archive snapshot
- Merge results (if available)
- Update performance tracker

### 4. Start the FastAPI endpoint (optional)

```bash
API_KEY="choose-a-secret" uvicorn src.api.main:APP --reload --port 8000
```

### 5. Generate GitHub Pages locally

```bash
python scripts/generate_github_pages.py
```

This creates `football/index.html` from the latest snapshot and results.

---

## Project Structure

```
.
├── data/
│   ├── raw/football_data/       # Downloaded raw CSVs
│   └── processed/               # Cleaned data, combined odds, results_merged.csv
├── models/
│   └── weekly/homewin/          # Versioned LightGBM model, feature list, metadata
├── jobs/
│   ├── scrape_matches.py
│   ├── train_model.py
│   ├── build_upcoming_features.py
│   ├── build_predictions_snapshot.py
│   ├── publish_snapshot.py
│   ├── deliver_telegram.py
│   ├── check_upcoming_matches.py
│   ├── merge_results.py
│   └── run_weekly_pipeline.sh
├── scripts/
│   ├── generate_github_pages.py
│   ├── smoke_test.sh
│   └── ...
├── src/
│   ├── api/
│   │   └── main.py               # FastAPI app
│   └── metrics.py                # Prometheus metrics
├── monitoring/
│   ├── prometheus/
│   ├── grafana/dashboards/
│   └── alertmanager/
├── tests/
├── .github/workflows/
│   ├── weekly-pipeline.yml
│   ├── post-match-results.yml
│   ├── deploy-football-predictions.yml
│   └── ci.yml
├── artifacts/                    # Training reports, evaluation outputs
├── snapshots/                    # Latest snapshot and archive
└── README.md
```

---

## Features

### Data Pipeline

- Scrapes fixtures from Premier League API and odds from The-Odds-API (h2h, totals, spreads)
- Merges bookmaker odds with fallback logic
- Standardises team names
- Computes rolling form features
- Handles Asian handicap lines and aggregates

### Modelling

- LightGBM classifier with versioned artefacts
- Automated hyperparameter tuning
- Feature importance analysis
- Calibrated probability outputs

### Evaluation & Tracking

- Overall accuracy (50% threshold)
- Value bet detection (model_prob > implied_prob)
- Value accuracy and profit tracking
- Recent results displayed on live page
- Model training accuracy displayed

### Delivery

- Telegram digest with `[VALUE]` / `[FADE]` tags
- Live GitHub Pages with predictions, tracker, and recent results
- FastAPI endpoint serving latest snapshot (optional)

### Monitoring

- Prometheus metrics for pipeline health (`pipeline_runs_total`, `snapshot_age_seconds`, etc.)
- Grafana dashboard for real-time monitoring
- Alertmanager alerts for stale snapshots (optional)

---

## Running Locally

### Full pipeline

```bash
bash jobs/run_weekly_pipeline.sh
```

### Update results manually

```bash
python jobs/scrape_matches.py --in-place
python jobs/merge_results.py
python scripts/generate_github_pages.py
```

### Start API server

```bash
API_KEY="choose-a-secret" uvicorn src.api.main:APP --reload --port 8000
```

### Smoke tests

```bash
bash scripts/smoke_test.sh
```

### Run unit tests

```bash
pytest
```

---

## API

| Endpoint              | Method | Description                                      |
|-----------------------|--------|--------------------------------------------------|
| `/predictions/latest` | GET    | Latest snapshot predictions                      |
| `/predictions/info`   | GET    | Model metadata                                   |
| `/ingest`             | POST   | Ingest new rows (idempotent)                     |
| `/metrics`            | GET    | Prometheus metrics                               |
| `/update_metrics`     | POST   | Refresh pipeline metrics (called automatically)  |

---

## Monitoring & Observability

The Docker Compose stack runs Prometheus, Grafana, Alertmanager, and a webhook receiver.  
See `DEVELOPER.md` for setup and configuration.

Key metrics:

- `pipeline_runs_total`
- `snapshot_age_seconds`
- `predictions_generated`
- `odds_available_count`

Grafana dashboard: import `monitoring/grafana/dashboards/pipeline_health.json` (or the current dashboard file).

---

## Results & Evaluation

- Performance tracker on the live page shows overall accuracy, value bet performance, and cumulative profit.
- Recent results section displays completed matches with score, predicted outcome, and correct/incorrect.
- Evaluation notebooks and calibration metrics are in `notebooks/` and `artifacts/`.

---

## Changelog

### September 2026 – Full Automation

- Added Post Match Results Update workflow (daily result merging)
- Fixed timezone guard for scheduled runs
- Added Recent Results section to live page
- Added model accuracy commit to pipeline

### August 2026 – Live Season Start

- Updated to 2026–27 season URL
- Integrated Asian handicap odds
- Deployed live GitHub Pages with performance tracker
- Automated Telegram delivery of pre‑match picks
- Added value/fade badges

### Earlier

- FastAPI snapshot endpoint
- Prometheus/Grafana monitoring
- Idempotent ingest and CI tests
- LightGBM model and evaluation pipeline

---

## Next Steps

- Add more bookmakers / markets
- Extend to other targets (over/under, draw, away win)
- Improve model calibration
- Add admin UI for delivery management
- Continue refining value bet strategy

---

## Acknowledgements

Data sources: [Football-Data.co.uk](https://www.football-data.co.uk) and [The-Odds-API](https://the-odds-api.com).  
This project is for educational and sports analytics purposes only.
