# ⚽ EPL Home-Win Predictor

End-to-end machine learning pipeline for predicting Premier League **home-win** outcomes.  
Fully automated and running for the **2026–27 season**.

[![CI](https://github.com/Shab00/Shab00.github.io/actions/workflows/ci.yml/badge.svg)](https://github.com/Shab00/Shab00.github.io/actions)

**Live dashboard:** https://shab00.github.io/football/  
**Telegram channel:** https://t.me/HomeWinPrediction  
**ML Experiments:** https://dagshub.com/Shab00/Over-Under2.5Goals/experiments

---

## Overview

Predicts whether the home team will win each Premier League fixture. Covers the full ML lifecycle:

- Automated fixture and odds scraping (football-data.co.uk)
- Feature engineering: rolling form, market odds, team encoding, Asian handicap
- LightGBM binary classifier with versioned artefacts tracked via MLflow on Dagshub
- Calibrated probability outputs with value-gap detection vs bookmaker odds
- AI pundit agent (GPT-4o-mini) generating written weekly strategy per fixture
- Live React dashboard deployed to GitHub Pages
- Telegram delivery of pre-match picks with value/fade tags
- Post-match results merging and performance tracking via Supabase

**Target variable:** `HomeWin` (FTR == 'H')  
**Current accuracy:** ~65% overall · F1 ~0.59

---

## Architecture

```
Scrape fixtures + odds (football-data.co.uk)
↓
Feature engineering (rolling form, market odds, Asian handicap)
↓
Train LightGBM model → log artefacts to MLflow (Dagshub)
↓
Generate predictions snapshot → write to Supabase
↓
AI Pundit (GPT-4o-mini) generates per-fixture strategy → validated via Pydantic v2
↓
Telegram digest delivered · React dashboard reads from Supabase · GitHub Pages deployed
↓
Daily: merge post-match results → update performance tracker in Supabase
```

---

## AI Pundit Agent

GPT-4o-mini generates written betting strategy for every gameweek fixture.

- Daily injury news scraped from NewsNow, accumulated in a compound knowledge base
- Past strategies archived with outcomes — system learns from what worked
- FAISS vector store activates after 20 scored strategies for similarity retrieval
- LLM receives clean pre-computed facts (form, H2H, value gaps) — never raw numbers
- Pydantic v2 schema validation on every GPT output
- Graceful fallback to model signals if OpenAI is unavailable
- `betting_category` (back_home / strong_fade / double_chance / avoid) computed in Python, never overridden by the LLM

---

## Automated Workflows (GitHub Actions)

| Workflow | Schedule | What it does |
|---|---|---|
| Weekly Pipeline | ~1hr before each kick-off slot | Scrape odds → train model → generate predictions → write to Supabase → send Telegram → deploy |
| Post Match Results Update | Daily 08:00 UTC | Merge results → update performance tracker in Supabase → deploy |
| Daily News Scrape | Daily 10:00 UTC | Scrape injury/team news → update knowledge base |
| Deploy to GitHub Pages | On pipeline completion | Build and deploy React dashboard |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Model | LightGBM (binary classifier) |
| Experiment tracking | MLflow → Dagshub |
| Backend / database | Supabase (PostgreSQL) |
| Frontend | React + TypeScript, deployed to GitHub Pages |
| Pundit agent | GPT-4o-mini via OpenAI API |
| Schema validation | Pydantic v2 |
| Delivery | Telegram Bot API |
| CI/CD | GitHub Actions |

---

## Environment Variables

```bash
# Odds and data
ODDS_API_KEY=

# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# OpenAI
OPENAI_API_KEY=

# Supabase
SUPABASE_URL=
SUPABASE_KEY=
DATABASE_URL=           # postgres:// connection string for psycopg2

# MLflow / Dagshub
MLFLOW_TRACKING_URI=
MLFLOW_TRACKING_USERNAME=
MLFLOW_TRACKING_PASSWORD=   # Dagshub token
```

---

## Running Locally

```bash
pip install -r requirements.txt

# Full weekly pipeline
bash jobs/run_weekly_pipeline.sh

# Update results manually
python jobs/merge_results.py

# Run tests
pytest
```

---

## Performance

- **Overall accuracy:** ~65% (50% threshold classifier)
- **Fade picks accuracy:** ~66%
- **Back home accuracy:** ~64%
- **Edge P&L:** tracked live on dashboard
- Calibration table and rolling accuracy visible on live page

---

## Changelog

### October 2026
- Migrated predictions storage and performance tracking to Supabase
- React + TypeScript dashboard replacing static HTML
- AI Pundit agent with RAG knowledge base and FAISS retrieval
- Market odds (B365H/D/A) added as normalised training features
- betting_category field enforced in Python (back_home / strong_fade / double_chance / avoid)
- MLflow experiment tracking via Dagshub HTTP basic auth

### September 2026
- Post Match Results Update workflow (daily result merging)
- Recent Results section added to live page
- Timezone guard for scheduled runs

### August 2026
- 2026–27 season live
- Asian handicap odds integrated
- Telegram delivery with value/fade badges
- GitHub Pages performance tracker

---

## Acknowledgements

Data: [Football-Data.co.uk](https://www.football-data.co.uk) · [The-Odds-API](https://the-odds-api.com)  
For educational and sports analytics purposes only.
