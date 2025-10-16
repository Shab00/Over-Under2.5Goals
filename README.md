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
