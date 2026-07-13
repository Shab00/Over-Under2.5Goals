from __future__ import annotations

import requests
import pandas as pd
import joblib
import numpy as np
import datetime
import re
from pathlib import Path
import sys

# --------- CONFIG ---------
BASE = Path(".").resolve()
output_all = BASE / "data/raw/football_data/premier_league_2025_26_fixtures.csv"
output_upcoming = BASE / "data/processed/premier_league_2025_26_upcoming_prediction_template.csv"
output_annotated = BASE / "data/processed/premier_league_2025_26_upcoming_with_teams_and_date.csv"
feature_path = BASE / "models/weekly/homewin/feature_list_20260327T205139Z.pkl"
engineered_history_path = BASE / "data/processed/engineered_train_features.csv"

API_KEY = 'f91688b2469810e18dbf6649b7d462fe'
sport_key = 'soccer_epl'
region = 'uk,eu'
markets = 'h2h,totals,spreads'
url = (f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
       f"?apiKey={API_KEY}&regions={region}&markets={markets}")

TEAM_MAP = {
    'manchester united': 'Man United',
    'man utd': 'Man United',
    'manchester city': 'Man City',
    'man city': 'Man City',
    'wolves': 'Wolves',
    'wolverhampton wanderers': 'Wolves',
    'nottingham forest': "Nott'm Forest",
    'west bromwich albion': 'West Brom',
    'west ham united': 'West Ham',
    'newcastle united': 'Newcastle',
    'tottenham hotspur': 'Tottenham',
    'leeds united': 'Leeds',
    'leicester city': 'Leicester',
    'sheffield united': 'Sheffield United',
    'crystal palace': 'Crystal Palace',
    'aston villa': 'Aston Villa',
    'brighton & hove albion': 'Brighton',
    'brighton and hove albion': 'Brighton',
    'bournemouth': 'Bournemouth',
    'liverpool': 'Liverpool',
    'chelsea': 'Chelsea',
    'arsenal': 'Arsenal',
    'brentford': 'Brentford',
    'burnley': 'Burnley',
    'luton town': 'Luton',
    'fulham': 'Fulham',
    'everton': 'Everton'
}
def standardize_team(val):
    if pd.isna(val):
        return val
    t = str(val).strip().lower()
    t = re.sub(r'\s+', ' ', t)
    return TEAM_MAP.get(t, val if isinstance(val, str) else str(val))

def clean_team_names(df, cols=("HomeTeam", "AwayTeam")):
    for col in cols:
        if col in df.columns:
            df[col] = df[col].apply(standardize_team)
    return df

def add_rolling_features(df, n_matches=5):
    df = df.copy()
    df = df.sort_values(["Date", "HomeTeam", "AwayTeam"]).reset_index(drop=True)
    df["FTHG"] = pd.to_numeric(df["FTHG"], errors="coerce")
    df["FTAG"] = pd.to_numeric(df["FTAG"], errors="coerce")
    df["HomeTeam_mean_FTHG"] = (
        df.groupby("HomeTeam")["FTHG"].apply(lambda x: x.shift(1).expanding().mean()).reset_index(level=0, drop=True)
    )
    df["AwayTeam_mean_FTAG"] = (
        df.groupby("AwayTeam")["FTAG"].apply(lambda x: x.shift(1).expanding().mean()).reset_index(level=0, drop=True)
    )
    records = []
    for idx, row in df.iterrows():
        past_home = df[
            (df["HomeTeam"] == row["HomeTeam"]) &
            (df["Date"] < row["Date"]) &
            df["FTHG"].notna()
        ].sort_values("Date").tail(n_matches)
        home_gf = past_home["FTHG"].mean() if not past_home.empty else np.nan
        home_ga = past_home["FTAG"].mean() if not past_home.empty else np.nan
        home_pts = past_home.apply(lambda r: 3 if r["FTHG"] > r["FTAG"] else (1 if r["FTHG"] == r["FTAG"] else 0), axis=1).sum() if not past_home.empty else np.nan
        past_away = df[
            (df["AwayTeam"] == row["AwayTeam"]) &
            (df["Date"] < row["Date"]) &
            df["FTAG"].notna()
        ].sort_values("Date").tail(n_matches)
        away_gf = past_away["FTAG"].mean() if not past_away.empty else np.nan
        away_ga = past_away["FTHG"].mean() if not past_away.empty else np.nan
        away_pts = past_away.apply(lambda r: 3 if r["FTAG"] > r["FTHG"] else (1 if r["FTAG"] == r["FTAG"] else 0), axis=1).sum() if not past_away.empty else np.nan
        records.append({
            "HomeRecentGF": home_gf,
            "HomeRecentGA": home_ga,
            "HomeRecentPts": home_pts,
            "AwayRecentGF": away_gf,
            "AwayRecentGA": away_ga,
            "AwayRecentPts": away_pts,
        })
    roll_df = pd.DataFrame(records, index=df.index)
    for col in roll_df.columns:
        df[col] = roll_df[col].values
    return df

def main():
    print("[upcoming_features] Start building upcoming fixtures/features with odds")
    # --- 1. Load engineered match data (history) ---
    df_hist = pd.read_csv(engineered_history_path, low_memory=False)
    df_hist["Date"] = pd.to_datetime(df_hist["Date"], errors="coerce")
    if "Kickoff" not in df_hist.columns:
        df_hist["Kickoff"] = df_hist["Date"]
    df_hist = clean_team_names(df_hist)

    # --- 2. Scrape all upcoming fixtures ---
    BASE_URL = "https://sdp-prem-prod.premier-league-prod.pulselive.com/api/v2/matches"
    competition_id, season_id = 8, 2025
    all_rows = []
    for mw in range(1, 39):
        params = {
            "competition": competition_id,
            "season": season_id,
            "matchweek": mw,
            "_limit": 20
        }
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(BASE_URL, params=params, headers=headers)
        js = resp.json()
        for match in js.get("data", []):
            home = match.get("homeTeam", {}).get("name", "")
            away = match.get("awayTeam", {}).get("name", "")
            kickoff = match.get("kickoff", "")
            matchweek = match.get("matchWeek", "")
            match_id = match.get("matchId", "")
            all_rows.append({
                "MatchWeek": matchweek,
                "HomeTeam": home,
                "AwayTeam": away,
                "FTHG": np.nan,   
                "FTAG": np.nan,
                "Kickoff": kickoff,
                "MatchId": match_id
            })

    df_fixtures = pd.DataFrame(all_rows)
    df_fixtures["Date"] = pd.to_datetime(df_fixtures["Kickoff"], errors="coerce")
    df_fixtures = clean_team_names(df_fixtures)
    output_all.parent.mkdir(parents=True, exist_ok=True)
    df_fixtures.to_csv(output_all, index=False)

    # --- 3. Add missing columns, concat with history ---
    needed_cols = set(df_hist.columns)
    missing_cols = needed_cols - set(df_fixtures.columns)
    fixture_add = pd.DataFrame({col: np.nan for col in missing_cols}, index=df_fixtures.index)
    df_fixtures = pd.concat([df_fixtures, fixture_add], axis=1)[df_hist.columns]
    df_all = pd.concat([df_hist, df_fixtures], ignore_index=True)
    df_all = df_all.sort_values(["Date", "HomeTeam", "AwayTeam"]).reset_index(drop=True)

    # --- 4. Add rolling features ---
    df_all = add_rolling_features(df_all, n_matches=5)

    # --- 5. Filter to only unplayed future matches ---
    mask_upcoming = (
        (df_all["FTHG"].isna() | (df_all["FTHG"].astype(str).str.strip() == ""))
        & (df_all["FTAG"].isna() | (df_all["FTAG"].astype(str).str.strip() == ""))
    )
    today_date = pd.Timestamp.today().date()
    df_upcoming = df_all[mask_upcoming & (df_all["Date"].dt.date >= today_date)].copy()

    # ---- OFF-SEASON GUARD: If no upcoming matches, exit gracefully and create empty outputs ----
    if df_upcoming.empty:
        print("[upcoming_features][INFO] No upcoming fixtures found (off-season). Exiting cleanly.")
        output_upcoming.parent.mkdir(parents=True, exist_ok=True)
        output_annotated.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame().to_csv(output_upcoming, index=False)
        pd.DataFrame().to_csv(output_annotated, index=False)
        sys.exit(0)

    # --- 6. Fill in odds for upcoming games ---
    df_upcoming = clean_team_names(df_upcoming, cols=["HomeTeam", "AwayTeam"])
    df_upcoming['home_team'] = df_upcoming['HomeTeam'].str.strip().str.lower()
    df_upcoming['away_team'] = df_upcoming['AwayTeam'].str.strip().str.lower()
    df_upcoming['date'] = pd.to_datetime(df_upcoming['Date']).dt.tz_localize(None).dt.normalize()

    response = requests.get(url)
    data = response.json()
    if not isinstance(data, list):
        print("[upcoming_features][error] Odds API error or quota issue:", data)
        raise Exception("Odds API error.")

    all_rows = []
    for event in data:
        ev = {
            "date": pd.to_datetime(event.get("commence_time")).tz_localize(None).normalize(),
            "home_team": event.get("home_team"),
            "away_team": event.get("away_team")
        }
        ev = clean_team_names(pd.DataFrame([ev]), cols=["home_team", "away_team"]).iloc[0].to_dict()
        ev["home_team"] = str(ev["home_team"]).strip().lower()
        ev["away_team"] = str(ev["away_team"]).strip().lower()

        for bookmaker in event.get("bookmakers", []):
            book = bookmaker.get("key", "")
            for market in bookmaker.get("markets", []):
                mkt = market.get("key", "")
                for out in market.get("outcomes", []):
                    if mkt == "h2h":
                        if out["name"] == event["home_team"]:
                            col = f"{book}_H"
                        elif out["name"] == event["away_team"]:
                            col = f"{book}_A"
                        elif out["name"].lower() == "draw":
                            col = f"{book}_D"
                        else:
                            col = f"{book}_h2h_{out['name']}"
                        ev[col] = out["price"]
                    elif mkt == "totals":
                        sign = ">" if out["name"].lower() == "over" else "<"
                        pt = out.get("point", "")
                        col = f"{book}_{sign}{pt}"
                        ev[col] = out["price"]
                    elif mkt == "spreads":
                        side = "H" if out["name"] == event["home_team"] else "A"
                        pt = out.get("point", "")
                        col = f"{book}_AH{side}_{pt}"
                        ev[col] = out["price"]
        all_rows.append(ev)
    odds_df = pd.DataFrame(all_rows)
    odds_df['date'] = pd.to_datetime(odds_df['date']).dt.tz_localize(None).dt.normalize()
    odds_df['home_team'] = odds_df['home_team'].str.strip().str.lower()
    odds_df['away_team'] = odds_df['away_team'].str.strip().str.lower()
    odds_df = odds_df.copy()

    print("\n--- Odds API Events Loaded ---")
    print(odds_df[["date", "home_team", "away_team"]])
    print(f"Games with odds in API: {len(odds_df)}")

    merged = df_upcoming.merge(
        odds_df,
        on=['date', 'home_team', 'away_team'],
        how='left',
        suffixes=('', '_odds')
    )

    # --- 7. Odds mapping and fallback ---
    market_map = {
        'B365H': ['bet365_H', 'pinnacle_H', 'williamhill_H', 'betway_H'],
        'B365D': ['bet365_D', 'pinnacle_D', 'williamhill_D', 'betway_D'],
        'B365A': ['bet365_A', 'pinnacle_A', 'williamhill_A', 'betway_A'],
        'PSH':    ['pinnacle_H', 'bet365_H', 'williamhill_H'],
        'PSD':    ['pinnacle_D', 'bet365_D', 'williamhill_D'],
        'PSA':    ['pinnacle_A', 'bet365_A', 'williamhill_A'],
        'WHH':    ['williamhill_H', 'bet365_H'],
        'WHD':    ['williamhill_D', 'bet365_D'],
        'WHA':    ['williamhill_A', 'bet365_A'],
        'LBH':    ['ladbrokes_uk_H', 'bet365_H'],
        'LBD':    ['ladbrokes_uk_D', 'bet365_D'],
        'LBA':    ['ladbrokes_uk_A', 'bet365_A'],
        'GBH':    ['gamebookers_H', 'bet365_H'],
        'GBD':    ['gamebookers_D', 'bet365_D'],
        'GBA':    ['gamebookers_A', 'bet365_A'],
        'B365>2.5': ['bet365_>2.5', 'pinnacle_>2.5', 'betway_>2.5'],
        'B365<2.5': ['bet365_<2.5', 'pinnacle_<2.5', 'betway_<2.5'],
        'P>2.5':    ['pinnacle_>2.5', 'bet365_>2.5', 'betway_>2.5'],
        'P<2.5':    ['pinnacle_<2.5', 'bet365_<2.5', 'betway_<2.5'],
        # etc
    }

    for col in df_upcoming.columns:
        if col in market_map and col in merged.columns:
            for fallback in market_map[col]:
                if fallback in merged.columns:
                    merged[col] = merged[col].fillna(merged[fallback])

    for col in df_upcoming.columns:
        if col in merged.columns:
            if col.endswith('H') and not any(x in col for x in ('AH', 'SH', 'CH', 'HH')) and col not in ['HomeTeam']:
                poss = [c for c in merged.columns if c.endswith('_H') and c != col]
                mask_empty = merged[col].isna()
                for fallback in poss:
                    merged.loc[mask_empty, col] = merged.loc[mask_empty, col].fillna(merged.loc[mask_empty, fallback])
                    mask_empty = merged[col].isna()
            elif col.endswith('D') and not any(x in col for x in ('AD', 'AHD')) and col not in ['DayOfWeek']:
                poss = [c for c in merged.columns if c.endswith('_D') and c != col]
                mask_empty = merged[col].isna()
                for fallback in poss:
                    merged.loc[mask_empty, col] = merged.loc[mask_empty, col].fillna(merged.loc[mask_empty, fallback])
                    mask_empty = merged[col].isna()
            elif col.endswith('A') and not any(x in col for x in ('HA', 'AHA')) and col not in ['AwayTeam']:
                poss = [c for c in merged.columns if c.endswith('_A') and c != col]
                mask_empty = merged[col].isna()
                for fallback in poss:
                    merged.loc[mask_empty, col] = merged.loc[mask_empty, col].fillna(merged.loc[mask_empty, fallback])
                    mask_empty = merged[col].isna()
            elif '>2.5' in col:
                poss = [c for c in merged.columns if '>2.5' in c and c != col]
                mask_empty = merged[col].isna()
                for fallback in poss:
                    merged.loc[mask_empty, col] = merged.loc[mask_empty, col].fillna(merged.loc[mask_empty, fallback])
                    mask_empty = merged[col].isna()
            elif '<2.5' in col:
                poss = [c for c in merged.columns if '<2.5' in c and c != col]
                mask_empty = merged[col].isna()
                for fallback in poss:
                    merged.loc[mask_empty, col] = merged.loc[mask_empty, col].fillna(merged.loc[mask_empty, fallback])
                    mask_empty = merged[col].isna()

    final_columns = list(df_upcoming.columns)
    final_df = merged[final_columns]
    final_df.to_csv(BASE / "data/processed/updated_fixtures_with_odds.csv", index=False)

    # Save model-ready template
    feature_list = joblib.load(feature_path)
    for col in feature_list:
        if col not in final_df.columns:
            final_df[col] = np.nan
    df_model_ready = final_df[feature_list].copy()
    output_upcoming.parent.mkdir(parents=True, exist_ok=True)
    df_model_ready.to_csv(output_upcoming, index=False)

    # Save annotated DataFrame
    df_annotated = final_df.copy()
    df_annotated['Year'] = pd.to_datetime(df_annotated['Date'], errors="coerce").dt.year
    df_annotated['Month'] = pd.to_datetime(df_annotated['Date'], errors="coerce").dt.month
    df_annotated['DayOfWeek'] = pd.to_datetime(df_annotated['Date'], errors="coerce").dt.dayofweek
    annotate_front = [c for c in ["HomeTeam", "AwayTeam", "Date", "Year", "Month", "DayOfWeek"] if c in df_annotated.columns]
    df_annotated = df_annotated[annotate_front + [c for c in df_annotated.columns if c not in annotate_front]]
    output_annotated.parent.mkdir(parents=True, exist_ok=True)
    df_annotated.to_csv(output_annotated, index=False)

    odds_keys = set(zip(odds_df['date'], odds_df['home_team'], odds_df['away_team']))
    fixture_keys = set(zip(df_upcoming['date'], df_upcoming['home_team'], df_upcoming['away_team']))
    unmatched = fixture_keys - odds_keys

    print("\n--- Unmatched fixture keys (no odds found for these):")
    for tup in unmatched:
        print(tup)
    print(f"Count with no odds: {len(unmatched)}")

    print(f"\nModel-ready prediction template saved to {output_upcoming}, shape: {df_model_ready.shape}")
    print(f"Annotated template with teams/dates/stats saved to {output_annotated}, shape: {df_annotated.shape}")
    print(df_annotated[["HomeTeam", "AwayTeam", "HomeTeam_mean_FTHG", "AwayTeam_mean_FTAG", "HomeRecentGF", "AwayRecentGF"]].head())

    print("✅ Done! All future odds columns filled and all artifacts exported.")

if __name__ == "__main__":
    main()
