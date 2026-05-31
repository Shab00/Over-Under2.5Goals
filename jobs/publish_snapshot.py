import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
import os
import numpy as np

ARTIFACT_FILE = Path(os.getenv("ARTIFACT_FILE", "artifacts/premier_league_2025_26_predictions.csv"))
OUT_LATEST = Path(os.getenv("OUT_LATEST", "snapshots/predictions_latest.csv"))

CANONICAL_HEADER = (
    "match_id,kickoff_time_utc,home_team,away_team,prob_homewin,pred_label,"
    "odds_B365H,is_predicted_fixture,generated_at\n"
)

def main():
    if not ARTIFACT_FILE.exists():
        raise FileNotFoundError(f"[publish] missing input predictions file: {ARTIFACT_FILE}")

    OUT_LATEST.parent.mkdir(parents=True, exist_ok=True)

    try:
        df = pd.read_csv(ARTIFACT_FILE)
    except pd.errors.EmptyDataError:
        print(f"[publish][INFO] predictions artifact is empty (off-season detected): {ARTIFACT_FILE}")
        OUT_LATEST.write_text(CANONICAL_HEADER)
        return 0

    if df.empty:
        print(f"[publish][INFO] input predictions file is empty: {ARTIFACT_FILE}")
        OUT_LATEST.write_text(CANONICAL_HEADER)
        return 0

    generated_at = datetime.now(timezone.utc).isoformat()
    df['generated_at'] = generated_at
    df = df.rename(columns={
        "date": "kickoff_time_utc",
        "home": "home_team",
        "away": "away_team",
        "prob_home": "prob_homewin",
    })

    if 'odds_B365H' in df.columns:
        df['is_predicted_fixture'] = df['odds_B365H'].apply(
            lambda x: int(pd.notnull(x) and isinstance(x, (float, int, np.floating, np.integer)))
        )
    else:
        df['is_predicted_fixture'] = 0

    canonical_cols = [
        "match_id",
        "kickoff_time_utc",
        "home_team",
        "away_team",
        "prob_homewin",
        "pred_label",
        "odds_B365H",
        "is_predicted_fixture",
        "generated_at"
    ]
    df = df[[c for c in canonical_cols if c in df.columns]]
    df.to_csv(OUT_LATEST, index=False)
    print(f"[publish] published all prediction rows to {OUT_LATEST}")

    return 0

if __name__ == "__main__":
    main()
