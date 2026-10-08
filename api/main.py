from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import joblib
import numpy as np
import glob
from pathlib import Path

app = FastAPI(title="EPL Home Win Predictor", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load latest model
def load_latest_model():
    models_dir = Path("models/weekly/homewin")
    model_files = sorted(glob.glob(str(models_dir / "lightgbm_homewin_*.pkl")), reverse=True)
    feat_files = sorted(glob.glob(str(models_dir / "feature_list_*.pkl")), reverse=True)
    if not model_files or not feat_files:
        raise FileNotFoundError("No model found")
    model = joblib.load(model_files[0])
    features = joblib.load(feat_files[0])
    print(f"[api] loaded model: {model_files[0]}")
    return model, features

model, feature_list = load_latest_model()

class FixtureRequest(BaseModel):
    home_team: str
    away_team: str
    odds_home: float
    odds_draw: float
    odds_away: float

class PredictionResponse(BaseModel):
    home_team: str
    away_team: str
    prob_homewin: float
    signal: str
    betting_category: str

@app.get("/health")
def health():
    return {"status": "ok", "model_features": len(feature_list)}

@app.post("/predict", response_model=PredictionResponse)
def predict(fixture: FixtureRequest):
    try:
        # Build feature vector with zeros for all features
        X = np.zeros((1, len(feature_list)))
        df_input = dict(zip(feature_list, X[0]))

        # Fill in odds features where available
        odds_map = {
            "B365H": fixture.odds_home,
            "B365D": fixture.odds_draw,
            "B365A": fixture.odds_away,
        }
        for feat, val in odds_map.items():
            # Try to find matching feature name
            for f in feature_list:
                if feat.lower() in f.lower():
                    df_input[f] = val
                    break

        X_input = np.array([list(df_input.values())])
        prob = float(model.predict_proba(X_input)[0][1])

        if prob >= 0.55:
            signal = "Home"
            betting_category = "back_home"
        elif prob >= 0.45:
            signal = "Avoid"
            betting_category = "avoid"
        elif prob >= 0.30:
            signal = "Not Home"
            betting_category = "double_chance"
        else:
            signal = "Not Home"
            betting_category = "strong_fade"

        return PredictionResponse(
            home_team=fixture.home_team,
            away_team=fixture.away_team,
            prob_homewin=round(prob, 4),
            signal=signal,
            betting_category=betting_category,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
