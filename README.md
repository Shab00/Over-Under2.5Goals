Progress update (9 Nov): produced probabilistic match predictions (home-win) from a trained LightGBM model and saves reproducible prospective snapshots for business evaluation. Today I verified feature alignment, generated a predictions snapshot (probabilities, labels, odds and actuals), and ran initial betting diagnostics (edge, EV and realized PnL) to identify promising picks and data issues. Next steps are a manual audit of top edges, probability calibration, and plotting cumulative PnL/threshold metrics to inform a conservative staking rule.

Progress update (31 Oct): Pivoted to HomeWin; evaluated RF, Gradient Boosting, XGBoost and LightGBM — LightGBM is the current best performer (accuracy ~65.8%, F1 ~0.614). Performed threshold sweeps and betting simulations using bookmaker odds; remaining work includes advanced feature tuning, probability calibration, and final business visualizations and report. Next immediate step: focus on LightGBM-driven business visualizations and finalize the write-up for stakeholder presentation.

# Football Match Outcome Prediction

## Overview

This project utilizes data analysis and machine learning to predict football match outcomes, with a current focus on **HomeWin** (whether the home team wins). The repository includes code, data processing pipelines, and business simulation tools to evaluate and deploy predictive models for football analytics.

## Project Evolution

Originally focused on predicting over/under 2.5 goals in Premier League matches, the project has pivoted to maximize predictive accuracy for the "HomeWin" outcome across a large football dataset, leveraging advanced feature engineering and multiple modeling approaches.

---

## Features

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
  - Model packaging for API deployment (Flask/FastAPI), with cloud hosting instructions.
- **Documentation & Demo**:  
  - Clear README, technical report, and visualizations for stakeholders.

---

## Current Focus

- **Target Variable**: HomeWin (home team wins)
- **Key Goal**: Push predictive accuracy as close to 70% as possible; demonstrate real-world business value via simulation and decision support.

---

## Usage

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
     - uvicorn deployment.api:app --reload
   - (If no API provided, skip this step.)

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

- **Best Model**: Random Forest, XGBoost, and Logistic Regression all reach ~65–67% accuracy on the HomeWin task.
- **Top Features**: Market odds (B365H, WHA, IWA, VCH, VCA), team performance metrics.
- **Business Simulation**: Model-based betting strategies are benchmarked against naive approaches. Profit/loss, ROI, and win rates are clearly reported.

---

## Next Steps

- Continue model calibration and deployment.
- Explore live-data integration for real-time predictions.
- Extend model to other targets (e.g., over/under goals, away win, draws).

---

## Acknowledgments

This project is for educational and sports analytics purposes only. Data sources include [Football-Data.co.uk](https://www.football-data.co.uk/) and other open football statistics archives.

---

## License

[MIT License](LICENSE)
