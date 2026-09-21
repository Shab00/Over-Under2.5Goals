import pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import numpy as np

ARTIFACT_FILE = Path(os.getenv("ARTIFACT_FILE", "artifacts/premier_league_2025_26_predictions.csv"))
OUT_LATEST = Path(os.getenv("OUT_LATEST", "snapshots/predictions_latest.csv"))

CANONICAL_HEADER = (
    "match_id,kickoff_time_utc,home_team,away_team,prob_homewin,pred_label,"
    "odds_B365H,is_predicted_fixture,generated_at\n"
)

# A fixture whose kickoff is this many minutes in the past is treated as
# "already started" - its pre-kickoff prediction row is frozen rather than
# overwritten by a fresh (and by then meaningless) model run.
FREEZE_GRACE_MINUTES = 5


def _fixture_key(row) -> tuple[str, str, str]:
    """(home_team, away_team, kickoff date) - matches a fixture across runs
    without depending on exact kickoff time formatting."""
    kickoff = str(row.get("kickoff_time_utc", ""))
    return (str(row.get("home_team", "")), str(row.get("away_team", "")), kickoff[:10])


def freeze_pre_kickoff_predictions(
    new_df: pd.DataFrame, existing_path: Path, now: datetime
) -> pd.DataFrame:
    """Preserve pre-kickoff prediction rows from the existing snapshot so a
    mid-gameweek pipeline run (e.g. a weekly retrain firing between kickoff
    and full-time) never overwrites a fixture that has already started with
    fresh model output - the performance tracker depends on the prediction
    value that existed *before* the game kicked off.

    For each row in the new predictions:
    - if its kickoff has already passed (with a small grace window) AND a
      matching row exists in the previous snapshot, the OLD row is kept
      verbatim instead of the new one ("frozen").
    - otherwise the new row is used as normal.

    A fixture present in the new predictions but missing from the old
    snapshot is always kept as-is (nothing to freeze). A fixture present in
    the old snapshot but absent from the new predictions is dropped (it has
    left the schedule) - this happens naturally since only new_df's rows
    are iterated.

    If existing_path doesn't exist or can't be read, new_df is returned
    unchanged - there is nothing to freeze against yet.
    """
    if not existing_path.exists():
        return new_df

    try:
        existing_df = pd.read_csv(existing_path)
    except (pd.errors.EmptyDataError, FileNotFoundError):
        return new_df

    if existing_df.empty:
        return new_df

    existing_by_key = {_fixture_key(row): row for _, row in existing_df.iterrows()}
    cutoff = now - timedelta(minutes=FREEZE_GRACE_MINUTES)

    kept_rows = []
    for _, row in new_df.iterrows():
        kickoff_str = str(row.get("kickoff_time_utc", ""))
        kickoff_dt = pd.to_datetime(kickoff_str, errors="coerce", utc=True)
        already_started = pd.notna(kickoff_dt) and kickoff_dt < cutoff
        key = _fixture_key(row)

        if already_started and key in existing_by_key:
            kept_rows.append(existing_by_key[key])
            print(
                f"[publish] frozen pre-kickoff prediction: "
                f"{row.get('home_team')} vs {row.get('away_team')} "
                f"(kicked off {kickoff_str})"
            )
        else:
            kept_rows.append(row)

    return pd.DataFrame(kept_rows, columns=new_df.columns)

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

    now = datetime.now(timezone.utc)
    generated_at = now.isoformat()
    df['generated_at'] = generated_at

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

    # Freeze any fixture that has already kicked off to its pre-kickoff
    # prediction value from the existing snapshot, instead of letting a
    # mid-gameweek run overwrite it with fresh (now-meaningless) output.
    df = freeze_pre_kickoff_predictions(df, OUT_LATEST, now)

    df.to_csv(OUT_LATEST, index=False)
    print(f"[publish] published all prediction rows to {OUT_LATEST}")

    return 0

if __name__ == "__main__":
    main()
