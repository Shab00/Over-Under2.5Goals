# Football Match Outcome Prediction

## Overview

Recent work — Telegram & delivery
- Implemented a Dockerized FastAPI snapshot endpoint that serves calibrated model probabilities from reproducible CSV snapshots.
- Implemented a Telegram digest pipeline (scripts/send_telegram_digest.py) that fetches picks from the API, delivers them to a Telegram chat, and logs every delivery to deliveries.db (message_id, chat_id, sent_at, match rows). This pipeline has been tested end‑to‑end locally and in Docker.

This project utilizes data analysis and machine learning to predict football match outcomes, with a current focus on **HomeWin** (whether the home team wins). The repository includes code, data processing pipelines, and business simulation tools to evaluate and deploy predictive models for football analytics.

## Project Evolution

Recent work — Telegram & delivery
- Delivery logs (deliveries.db) now enable per‑user delivery history and basic ROI tracking so we can A/B test thresholds and message formats.
- The API + delivery pipeline is packaged for lightweight deployment in Docker/Colima.

Originally focused on predicting over/under 2.5 goals in Premier League matches, the project has pivoted to maximize predictive accuracy for the "HomeWin" outcome across a large football dataset, leveraging advanced feature engineering and multiple modeling approaches.

---

## Features

Recent work — Telegram & delivery
- The API exposes endpoints (/predictions/latest and /predictions/info) that the sender uses to assemble digests.
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

Recent work — Telegram & delivery
- Focused on snapshot‑based reproducibility: predictions are saved to CSV snapshots which are loaded by the API and used by the sender to ensure the exact rows sent are logged.
- Lightweight deployment: Docker + simple worker scheduler approach; sender can be run locally or as a one‑off Docker job.

- **Target Variable**: HomeWin (home team wins)
- **Key Goal**: Push predictive accuracy as close to 70% as possible; demonstrate real-world business value via simulation and decision support.

---

## Usage

Recent work — Telegram & delivery
- The README below includes exact commands to run the API, build the Docker image, and run the Telegram sender. The sender writes to deliveries.db in the repo so you have an auditable delivery history.

Quick start — get the project running and reproduce key results.

1. Install dependencies
   - pip install -r requirements.txt

2. Prepare data
   - Raw CSVs are in data/raw/csvFiles.  
   - Run the cleaning/feature pipeline from the notebooks or scripts to produce processed data in data/processed/. Example (notebook):
     - Open notebooks/firstIterration/dataCleaning.ipynb or notebooks/secondIterrationOdds/cleaningWithOdds-evaluation.ipynb and run the preprocessing cells.
   - Or run your processing script (if you have one) to generate:
     - data/processed/cleaned_data.csv
     - data/processed/combinedWithOdds.csv
     - data/processed/final_football_model_data.csv

3. Train / load models
   - Pretrained model artifacts are under models/:
     - models/thirdIterration/rf_HomeWin_best.pkl (Random Forest snapshot)
     - models/secondIterration/rf_Home_2plus_best.pkl (other iterations)
   - To retrain:
     - Open notebooks/thirdIterration/footballBoost.ipynb or notebooks/firstIterration/randomForrest.ipynb and run the training cells.
     - Or run your training script (e.g., src/train_lightgbm.py) if available.

4. Evaluate & compare models
   - Use notebooks/thirdIterration/testPipeline.ipynb or notebooks/secondIterrationOdds/modelProbabilitiesBusinessValue.ipynb to:
     - Produce predictions and probability outputs (saved to data/processed/over_under_test_probs.csv or similar).
     - Compare Random Forest / XGBoost / LightGBM performance and run threshold sweeps.

5. Run betting simulation
   - The betting simulation logic and evaluation data are in:
     - data/evaluation/ (recentGames and secondIterration folders)
     - notebooks/secondIterrationOdds/modelProbabilitiesBusinessValue.ipynb contains example simulation code.
   - Quick simulation workflow:
     - Load predictions CSV (predicted probabilities, odds, actual outcome).
     - Apply threshold (e.g., 0.50 or business threshold from analysis).
     - Compute profit/loss per match using bookmaker odds (B365H, etc.) and aggregate cumulative profit/ROI.
   - Example outputs are saved to data/processed/first_engineered_betting_features_evaluation.csv and over_under_test_probs.csv.

6. Quick checks and artifacts
   - Snapshot predictions for reproducibility:
     - Save predictions to predictions_lightgbm_snapshot.csv before running multiple sims.
   - Feature importances and reports:
     - Check notes/firstIterration/feature_importances.txt or print from model notebooks.

7. Notebooks & examples
   - notebooks/firstIterration — data cleaning and RF baseline
   - notebooks/secondIterrationOdds — odds-aware cleaning and business evaluation
   - notebooks/thirdIterration — boosting experiments and final pipeline

8. Running locally (optional)
   - If you have a small API (deployment code), run it locally with:
     - python -m uvicorn src.api.main:APP --reload --port 8000
   - Or use the helper:
     - ./run_api.sh <conda-env-name>

Where to look for results
- Models: models/
- Processed data & evaluation: data/processed/, data/evaluation/
- Notebooks (reproducible analysis): notebooks/
- Notes & feature audits: notes/

Short troubleshooting
- Missing packages: run pip install -r requirements.txt
- Large data files: keep raw CSVs out of git; generate processed files locally.
- If a notebook fails, re-run the preprocessing notebook to ensure expected data files are present in data/processed/.

---

## Results

Recent work — Telegram & delivery
- We validated the end‑to‑end flow: snapshot → API → Telegram digest → deliveries.db logging. Example run produced 5 picks delivered in a single digest and recorded with a message_id in deliveries.db.
- Deliveries logging enables per‑user ROI tracking and A/B experiments on thresholds and message formats.

Summary of modeling/evaluation results
- Snapshot from 10 Nov produced 269 prospective matches with feature alignment verified and Platt/isotonic calibration applied.
- Calibration and observed performance:
  - Raw Brier score: 0.238
  - Platt calibration Brier: 0.233
  - Isotonic calibration Brier: 0.222
- Business simulation (example run):
  - The model flagged 49 positive‑edge opportunities (theoretical sum EV ≈ +15.48 units).
  - Realized historical PnL on those bets in the test snapshot was ≈ −9.17 units (indicating overconfidence or problematic top edges).
- Best model family: Random Forest / XGBoost / Logistic Regression all in the ~65–67% accuracy range on HomeWin.

---

## Next Steps

Recent work — Telegram & delivery
- Use deliveries.db to set up A/B tests: e.g., compare threshold 0.50 vs 0.55 across user cohorts, and track per‑user ROI.
- Add a small admin UI to inspect deliveries and re‑send picks if needed; this will improve auditability for the closed beta.

- Continue model calibration and deployment.
- Explore live-data integration for real-time predictions.
- Extend model to other targets (e.g., over/under goals, away win, draws).

---

## Acknowledgments

This project is for educational and sports analytics purposes only. Data sources include [Football-Data.co.uk](https://www.football-data.co.uk/) and other open football statistics archives.

---

## License

[MIT License](LICENSE)
