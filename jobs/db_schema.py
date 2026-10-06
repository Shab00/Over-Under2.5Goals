#!/usr/bin/env python
"""Create PostgreSQL database schema for predictions, results, and strategy archive."""

import os
import sys
from dotenv import load_dotenv
import psycopg2

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("[db] ERROR: DATABASE_URL not set in .env")
    sys.exit(1)

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    # Create predictions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id SERIAL PRIMARY KEY,
            match_key VARCHAR(100) UNIQUE NOT NULL,
            kickoff_time TIMESTAMPTZ,
            home_team VARCHAR(100),
            away_team VARCHAR(100),
            prob_homewin FLOAT,
            pred_label INTEGER,
            odds_B365H FLOAT,
            signal VARCHAR(20),
            edge_label VARCHAR(10),
            betting_category VARCHAR(20),
            generated_at TIMESTAMPTZ,
            snapshot_file VARCHAR(200),
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_predictions_kickoff 
        ON predictions(kickoff_time)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_predictions_home_team 
        ON predictions(home_team)
    """)

    # Create results table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id SERIAL PRIMARY KEY,
            match_key VARCHAR(100) UNIQUE NOT NULL,
            kickoff_time TIMESTAMPTZ,
            home_team VARCHAR(100),
            away_team VARCHAR(100),
            FTR VARCHAR(2),
            FTHG INTEGER,
            FTAG INTEGER,
            home_win BOOLEAN,
            prediction BOOLEAN,
            correct BOOLEAN,
            implied_prob FLOAT,
            is_edge BOOLEAN,
            edge_correct BOOLEAN,
            is_fade BOOLEAN,
            fade_correct BOOLEAN,
            profit FLOAT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_results_kickoff 
        ON results(kickoff_time)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_results_match_key 
        ON results(match_key)
    """)

    # Create strategy_archive table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS strategy_archive (
            id SERIAL PRIMARY KEY,
            generated_at TIMESTAMPTZ UNIQUE,
            gameweek_start DATE,
            gameweek_end DATE,
            scored BOOLEAN DEFAULT FALSE,
            gameweek_summary TEXT,
            model_form TEXT,
            top_picks_json JSONB,
            strong_fades_json JSONB,
            double_chances_json JSONB,
            overall_accuracy FLOAT,
            edge_accuracy FLOAT,
            total_profit FLOAT,
            archive_file VARCHAR(200),
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()

    print("[db] Connected to Supabase PostgreSQL")
    print("[db] Schema created/verified — 3 tables ready")

except Exception as e:
    print(f"[db] ERROR: {e}")
    sys.exit(1)
