#!/usr/bin/env python
"""Save predictions, results, and strategy data to PostgreSQL."""

import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("[db] ERROR: DATABASE_URL not set in .env")
    sys.exit(1)

conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

predictions_saved = 0
results_saved = 0
strategies_saved = 0

# ============================================================================
# STEP 1: Save predictions from snapshots/predictions_latest.csv
# ============================================================================
try:
    predictions_csv = "snapshots/predictions_latest.csv"
    if Path(predictions_csv).exists():
        df_pred = pd.read_csv(predictions_csv)
        
        rows_to_insert = []
        for _, row in df_pred.iterrows():
            try:
                # Build match_key from date and teams
                kickoff_date = str(row["kickoff_time_utc"])[:10]
                match_key = f"{kickoff_date}|{row['home_team']}|{row['away_team']}"
                
                # Compute signal
                signal = "Home" if row["pred_label"] == 1 else "Not Home"
                
                # Compute betting_category based on prob_homewin thresholds
                prob = row["prob_homewin"]
                if prob >= 0.55:
                    betting_category = "back_home"
                elif prob >= 0.45:
                    betting_category = "avoid"
                elif prob >= 0.30:
                    betting_category = "double_chance"
                else:
                    betting_category = "strong_fade"
                
                # Compute edge_label
                odds_b365h = row["odds_B365H"]
                implied_prob = 1 / odds_b365h if odds_b365h > 0 else 0
                edge_label = "EDGE" if signal == "Home" and prob > implied_prob else "FADE"
                
                rows_to_insert.append((
                    match_key,
                    row["kickoff_time_utc"],
                    row["home_team"],
                    row["away_team"],
                    row["prob_homewin"],
                    row["pred_label"],
                    row["odds_B365H"],
                    signal,
                    edge_label,
                    betting_category,
                    row["generated_at"],
                    row.get("snapshot_file", "")
                ))
            except Exception as e:
                print(f"[db] Warning: Skipping prediction row: {e}")
                continue
        
        if rows_to_insert:
            sql_pred = """
                INSERT INTO predictions 
                (match_key, kickoff_time, home_team, away_team, prob_homewin, 
                 pred_label, odds_B365H, signal, edge_label, betting_category, 
                 generated_at, snapshot_file)
                VALUES %s
                ON CONFLICT (match_key) DO NOTHING
            """
            execute_values(cursor, sql_pred, rows_to_insert)
            predictions_saved = len(rows_to_insert)
            conn.commit()
except Exception as e:
    print(f"[db] Warning: Predictions insert failed: {e}")
    conn.rollback()

# ============================================================================
# STEP 2: Save results from data/processed/results_merged.csv
# ============================================================================
try:
    results_csv = "data/processed/results_merged.csv"
    if Path(results_csv).exists():
        df_res = pd.read_csv(results_csv)
        
        rows_to_insert = []
        for _, row in df_res.iterrows():
            try:
                # Only process rows where FTR is not null (match has been played)
                if pd.isna(row.get("FTR")):
                    continue
                
                kickoff_date = str(row["kickoff_time_utc"])[:10]
                match_key = f"{kickoff_date}|{row['home_team']}|{row['away_team']}"
                
                rows_to_insert.append((
                    match_key,
                    row["kickoff_time_utc"],
                    row["home_team"],
                    row["away_team"],
                    row["FTR"],
                    int(row["FTHG"]) if pd.notna(row["FTHG"]) else None,
                    int(row["FTAG"]) if pd.notna(row["FTAG"]) else None,
                    bool(row["home_win"]) if pd.notna(row["home_win"]) else None,
                    bool(row["prediction"]) if pd.notna(row["prediction"]) else None,
                    bool(row["correct"]) if pd.notna(row["correct"]) else None,
                    float(row["implied_prob"]) if pd.notna(row["implied_prob"]) else None,
                    bool(row["is_edge"]) if pd.notna(row["is_edge"]) else None,
                    bool(row["edge_correct"]) if pd.notna(row["edge_correct"]) else None,
                    bool(row["is_fade"]) if pd.notna(row["is_fade"]) else None,
                    bool(row["fade_correct"]) if pd.notna(row["fade_correct"]) else None,
                    float(row["profit"]) if pd.notna(row["profit"]) else None
                ))
            except Exception as e:
                print(f"[db] Warning: Skipping result row: {e}")
                continue
        
        if rows_to_insert:
            sql_res = """
                INSERT INTO results 
                (match_key, kickoff_time, home_team, away_team, FTR, FTHG, FTAG,
                 home_win, prediction, correct, implied_prob, is_edge, edge_correct,
                 is_fade, fade_correct, profit)
                VALUES %s
                ON CONFLICT (match_key) DO NOTHING
            """
            execute_values(cursor, sql_res, rows_to_insert)
            results_saved = len(rows_to_insert)
            conn.commit()
except Exception as e:
    print(f"[db] Warning: Results insert failed: {e}")
    conn.rollback()

# ============================================================================
# STEP 3: Save strategy archives from artifacts/strategy_archive/*.json
# ============================================================================
try:
    strategy_dir = Path("artifacts/strategy_archive")
    if strategy_dir.exists():
        for json_file in strategy_dir.glob("*.json"):
            try:
                with open(json_file) as f:
                    strategy_data = json.load(f)
                
                generated_at = strategy_data.get("generated_at")
                if not generated_at:
                    continue
                
                # Extract fields, default to NULL if not present
                gameweek_start = strategy_data.get("gameweek_start")
                gameweek_end = strategy_data.get("gameweek_end")
                scored = strategy_data.get("scored", False)
                gameweek_summary = strategy_data.get("gameweek_summary")
                model_form = strategy_data.get("model_form")
                top_picks = strategy_data.get("top_picks")
                strong_fades = strategy_data.get("strong_fades")
                double_chances = strategy_data.get("double_chances")
                
                # Upsert with ON CONFLICT DO UPDATE
                sql_strat = """
                    INSERT INTO strategy_archive 
                    (generated_at, gameweek_start, gameweek_end, scored, 
                     gameweek_summary, model_form, top_picks_json, 
                     strong_fades_json, double_chances_json, archive_file)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (generated_at) DO UPDATE SET
                        gameweek_start = EXCLUDED.gameweek_start,
                        gameweek_end = EXCLUDED.gameweek_end,
                        scored = EXCLUDED.scored,
                        gameweek_summary = EXCLUDED.gameweek_summary,
                        model_form = EXCLUDED.model_form,
                        top_picks_json = EXCLUDED.top_picks_json,
                        strong_fades_json = EXCLUDED.strong_fades_json,
                        double_chances_json = EXCLUDED.double_chances_json,
                        archive_file = EXCLUDED.archive_file
                """
                
                cursor.execute(
                    sql_strat,
                    (
                        generated_at,
                        gameweek_start,
                        gameweek_end,
                        scored,
                        gameweek_summary,
                        model_form,
                        json.dumps(top_picks) if top_picks else None,
                        json.dumps(strong_fades) if strong_fades else None,
                        json.dumps(double_chances) if double_chances else None,
                        json_file.name
                    )
                )
                strategies_saved += 1
                conn.commit()
            except Exception as e:
                print(f"[db] Warning: Skipping strategy file {json_file.name}: {e}")
                conn.rollback()
                continue
except Exception as e:
    print(f"[db] Warning: Strategy archive processing failed: {e}")
    conn.rollback()

# ============================================================================
# Close connection and print summary
# ============================================================================
cursor.close()
conn.close()

print(f"[db] Saved {predictions_saved} predictions to database")
print(f"[db] Saved {results_saved} results to database")
print(f"[db] Saved {strategies_saved} strategies to database")
