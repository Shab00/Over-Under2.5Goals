# Football Match Outcome Prediction

## Overview

Recent work — Telegram & delivery (see "Recent work" section below)
- Implemented a Dockerized FastAPI snapshot endpoint that serves calibrated model probabilities from reproducible CSV snapshots.
- Implemented a Telegram digest pipeline (`scripts/send_telegram_digest.py`) that fetches picks from the API, delivers them to a Telegram chat, and logs every delivery to `deliveries.db` (message_id, chat_id, sent_at, match rows). This pipeline has been tested end‑to‑end locally and in Docker.

This project utilizes data analysis and machine learning to predict football match outcomes, with a current focus on **HomeWin** (whether the home team wins). The repository includes code, data processing pipelines, and business simulation tools to evaluate and deploy predictive models for football analytics.

## Recent work — Telegram, delivery, idempotency & CI

- Delivery & auditability
  - End‑to‑end flow validated: snapshot → API → Telegram digest → `deliveries.db` logging.
  - Delivery logs include metadata (threshold, prob_col) so we can run per‑user A/B tests and measure ROI.
- Database hardening (idempotency)
  - Added `scripts/migrate_make_match_id_unique.sh` to dedupe existing rows and create a UNIQUE index on `match_id`.
  - Ingestion now enforces idempotency at the DB-level (prevents duplicates even if requests are retried or arrive concurrently).
- Tests & CI
  - Added `tests/test_idempotency.py` — integration smoke test that posts the same `match_id` twice and asserts the second is skipped.
  - Added `.github/workflows/ci.yml` — minimal GitHub Actions workflow that runs pytest on pushes and PRs.
- Repo hygiene & demo
  - Stopped tracking runtime DB (`data/deliveries.db`) and added it to `.gitignore`.
  - Demo snippet and CI badge added to README for easier review and demoing.

> If you ran the migration locally: `./scripts/migrate_make_match_id_unique.sh` will create a backup and index; local smoke tests and pytest passed on the release branch.

## Project Evolution

Originally focused on predicting over/under 2.5 goals in Premier League matches, the project has pivoted to maximize predictive accuracy for the "HomeWin" outcome across a large football dataset, leveraging advanced feature engineering and multiple modeling approaches.

---

## Features

- The API exposes endpoints (`/predictions/latest` and `/predictions/info`) that the sender uses to assemble digests.
- Delivery logging supports simple A/B testing: threshold and prob_col used for a run are recorded alongside message metadata.

- **Data Pipeline**:  
  - Ingestion, cleaning, and comprehensive feature engineering (market odds, team encoding, recent form, contextual variables).
- **Modeling**:  
  - Multiple classifiers tested, including Random Forest, Gradient Boosting, Logistic Regression, and MLP Neural Networks.
  - Hyperparameter tuning and feature importance analysis.
- **Evaluation**:  
  - Robust cross-validation, threshold tuning for business objectives (accuracy/F1), and error analysis.
- **Business Simulation**:  
  - Simulated betting strategies using model probabilities and bookmaker odds.
  - ROI, win rate, and profit/loss tracked and visualized.
- **Deployment Ready**:  
  - Model packaging for API deployment (FastAPI), with Docker instructions and a run helper script.
- **Documentation & Demo**:  
  - Clear README, technical report, and visualizations for stakeholders.

---

## Current Focus

- Focused on snapshot‑based reproducibility: predictions are saved to CSV snapshots which are loaded by the API and used by the sender to ensure the exact rows sent are logged.
- Lightweight deployment: Docker + simple worker scheduler approach; sender can be run locally or as a one‑off Docker job.

- **Target Variable**: HomeWin (home team wins)
- **Key Goal**: Push predictive accuracy as close to 70% as possible; demonstrate real-world business value via simulation and decision support.

---

## Usage

- The README includes exact commands to run the API, build the Docker image, and run the Telegram sender. The sender writes to `deliveries.db` in the repo so you have an auditable delivery history.

Quick start — get the project running and reproduce key results.

1. Install dependencies
   - `pip install -r requirements.txt`

2. Prepare data
   - Raw CSVs are in `data/raw/csvFiles`.  
   - Run the cleaning/feature pipeline from the notebooks or scripts to produce processed data in `data/processed/`. Example (notebook):
     - Open `notebooks/firstIterration/dataCleaning.ipynb` or `notebooks/secondIterrationOdds/cleaningWithOdds-evaluation.ipynb` and run the preprocessing cells.
   - Or run your processing script to generate:
     - `data/processed/cleaned_data.csv`
     - `data/processed/combinedWithOdds.csv`
     - `data/processed/final_football_model_data.csv`

3. Train / load models
   - Pretrained model artifacts are under `models/`.
   - To retrain: run the notebooks or training scripts provided.

4. Evaluate & compare models
   - Use evaluation notebooks to produce predictions and probability outputs and run threshold sweeps.

5. Run betting simulation
   - Load predictions CSV and apply business thresholds to compute PnL/ROI.

6. Quick checks and artifacts
   - Snapshot predictions for reproducibility: save predictions to a CSV before running simulations.
   - Feature importances and reports available in notes and notebooks.

7. Notebooks & examples
   - `notebooks/firstIterration` — data cleaning and RF baseline
   - `notebooks/secondIterrationOdds` — odds-aware cleaning and business evaluation
   - `notebooks/thirdIterration` — boosting experiments and final pipeline

8. Running locally
   - `API_KEY="choose-a-secret" uvicorn src.api.main:APP --reload --port 8000`
   - Or use `./run_api.sh <conda-env-name>` if available.

Where to look for results
- Models: `models/`
- Processed data & evaluation: `data/processed/`, `data/evaluation/`
- Notebooks (reproducible analysis): `notebooks/`
- Notes & feature audits: `notes/`

Short troubleshooting
- Missing packages: `pip install -r requirements.txt`
- Large data files: keep raw CSVs out of git; generate processed files locally.
- If a notebook fails, re-run the preprocessing notebook to produce expected data files.

---

## Results

- Validated end‑to‑end flow: snapshot → API → Telegram digest → `deliveries.db` logging.
- Deliveries logging enables per‑user ROI tracking and A/B experiments on thresholds and message formats.

Summary of modeling/evaluation results
- Calibration and observed performance metrics and business simulation outputs are in the notebooks and evaluation CSVs.

---

## Next Steps

- Use `deliveries.db` to run A/B tests on thresholds and message formats.
- Add a small admin UI to inspect deliveries and re‑send picks (improves auditability).
- Continue model calibration and explore live-data integration.
- Extend models to other targets (over/under, away win, draw).

---

## Acknowledgments

This project is for educational and sports analytics purposes only. Data sources include [Football-Data.co.uk](https://www.football-data.co.uk/) and other open football statistics archives.

---

## Demo

[![CI](https://github.com/Shab00/Over-Under2.5Goals/actions/workflows/ci.yml/badge.svg)](https://github.com/Shab00/Over-Under2.5Goals/actions)

Try the ingest endpoint (replace <URL> with the deployed URL):

```bash
curl -X POST '<URL>/ingest' -H 'Content-Type: application/json' -H 'X-API-KEY: choose-a-secret' -d '{"rows":[{"match_id":12345,"prob":0.5}],"source":"demo"}'
```
## License

[MIT License](LICENSE)
