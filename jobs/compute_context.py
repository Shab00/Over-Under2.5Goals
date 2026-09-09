#!/usr/bin/env python3
"""Pre-compute clean match-context facts for the AI pundit strategy agent.

Pure computation only: NO AI calls, NO maths left for the model. Reads the
raw pipeline data and writes ``artifacts/match_context.json`` so that
``jobs/generate_strategy.py`` only ever has to reason over tidy numbers.

Data sources
------------
snapshots/predictions_latest.csv     upcoming fixtures + model output
data/processed/combinedWithOdds.csv   full historical match results
data/processed/results_merged.csv     model track record
data/processed/news_context.json      injury / team-news headlines
"""

from __future__ import annotations

import difflib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

PREDICTIONS_CSV = Path("snapshots/predictions_latest.csv")
COMBINED_CSV = Path("data/processed/combinedWithOdds.csv")
RESULTS_CSV = Path("data/processed/results_merged.csv")
NEWS_JSON = Path("data/processed/news_context.json")
OUT_JSON = Path("artifacts/match_context.json")

LOOKAHEAD_DAYS = 7
FORM_N = 5
H2H_N = 5
PERF_N = 30
SEASON_START = pd.Timestamp("2026-08-01")  # start of the 26/27 season

# prediction-feed name -> variants that may appear as HomeTeam in combinedWithOdds
KNOWN_VARIANTS = {
    "Nott'm Forest": ["Nottingham Forest", "Nottm Forest"],
    "Man City": ["Manchester City"],
    "Man United": ["Manchester United", "Man Utd"],
    "Newcastle": ["Newcastle United", "Newcastle Utd"],
    "Leeds": ["Leeds United"],
    "Brighton": ["Brighton & Hove Albion", "Brighton and Hove Albion"],
    "Ipswich Town": ["Ipswich"],
    "Coventry City": ["Coventry"],
    "Hull City": ["Hull"],
    "Tottenham": ["Tottenham Hotspur", "Spurs"],
    "Bournemouth": ["AFC Bournemouth"],
    "Wolves": ["Wolverhampton", "Wolverhampton Wanderers"],
    "West Ham": ["West Ham United"],
    "Sheffield United": ["Sheffield Utd"],
    "QPR": ["Queens Park Rangers"],
    "West Brom": ["West Bromwich Albion", "West Brom"],
    "Leicester": ["Leicester City"],
    "Luton": ["Luton Town"],
}


def _norm(s: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


# --------------------------------------------------------------------------- #
# STEP 2 - team name normalisation map (built dynamically)
# --------------------------------------------------------------------------- #
def build_norm_map(names, hometeams) -> dict:
    ht_list = sorted(hometeams)
    ht_by_norm = {_norm(h): h for h in ht_list}
    mapping: dict[str, str | None] = {}
    for name in sorted({str(n) for n in names}):
        if name in hometeams:
            mapping[name] = name
            continue
        hit = ht_by_norm.get(_norm(name))
        if hit is None:
            for variant in KNOWN_VARIANTS.get(name, []):
                if variant in hometeams:
                    hit = variant
                    break
                if _norm(variant) in ht_by_norm:
                    hit = ht_by_norm[_norm(variant)]
                    break
        if hit is None:
            close = difflib.get_close_matches(name, ht_list, n=1, cutoff=0.7)
            if close:
                hit = close[0]
        mapping[name] = hit
    return mapping


# --------------------------------------------------------------------------- #
# Historical results helpers
# --------------------------------------------------------------------------- #
def load_history() -> pd.DataFrame:
    wanted = {"HomeTeam", "AwayTeam", "FTR", "FTHG", "FTAG", "Date", "DateParsed"}
    hist = pd.read_csv(
        COMBINED_CSV, low_memory=False, usecols=lambda c: c in wanted
    )
    hist["_date"] = pd.to_datetime(hist.get("DateParsed"), errors="coerce")
    if "Date" in hist.columns:
        missing = hist["_date"].isna()
        if missing.any():
            hist.loc[missing, "_date"] = pd.to_datetime(
                hist.loc[missing, "Date"], dayfirst=True, errors="coerce"
            )
    hist = hist.dropna(subset=["_date", "FTR"]).sort_values("_date")
    for col in ("FTHG", "FTAG"):
        hist[col] = pd.to_numeric(hist[col], errors="coerce").fillna(0)
    return hist


def _team_rows(hist: pd.DataFrame, team_canon: str) -> pd.DataFrame:
    """All games (home or away) involving the team."""
    return hist[(hist["HomeTeam"] == team_canon) | (hist["AwayTeam"] == team_canon)]


def _perspective(row, team_canon: str) -> tuple[str, float, float]:
    """(result, goals_for, goals_against) from the team's point of view."""
    if row["HomeTeam"] == team_canon:
        gf, ga = row["FTHG"], row["FTAG"]
        res = "W" if row["FTR"] == "H" else "D" if row["FTR"] == "D" else "L"
    else:
        gf, ga = row["FTAG"], row["FTHG"]
        res = "W" if row["FTR"] == "A" else "D" if row["FTR"] == "D" else "L"
    return res, gf, ga


def _points(res: str) -> int:
    return 3 if res == "W" else 1 if res == "D" else 0


def current_season(hist: pd.DataFrame, team_canon: str) -> tuple[int, int]:
    """Points and games played since SEASON_START, home + away combined."""
    d = _team_rows(hist, team_canon)
    d = d[d["_date"] >= SEASON_START]
    pts = sum(_points(_perspective(row, team_canon)[0]) for _, row in d.iterrows())
    return int(pts), int(len(d))


def team_form(hist: pd.DataFrame, team_canon: str | None) -> dict:
    """Current-season points + last-5 form (home AND away) from team perspective."""
    out = {"current_season_pts": 0, "current_season_games": 0,
           "pts_last5": 0, "gf_last5": 0, "ga_last5": 0,
           "wins_last5": 0, "form_string": ""}
    if not team_canon:
        return out

    out["current_season_pts"], out["current_season_games"] = current_season(hist, team_canon)

    d = (_team_rows(hist, team_canon)
         .sort_values("_date", ascending=False)
         .head(FORM_N)
         .iloc[::-1])  # chronological, most recent rightmost

    results, gf_tot, ga_tot = [], 0.0, 0.0
    for _, row in d.iterrows():
        res, gf, ga = _perspective(row, team_canon)
        results.append(res)
        gf_tot += gf
        ga_tot += ga

    out["pts_last5"] = int(sum(_points(r) for r in results))
    out["gf_last5"] = int(round(gf_tot))
    out["ga_last5"] = int(round(ga_tot))
    out["wins_last5"] = int(sum(1 for r in results if r == "W"))
    out["form_string"] = " ".join(results)
    return out


def head_to_head(hist: pd.DataFrame, home_canon: str | None, away_canon: str | None) -> dict:
    if not home_canon or not away_canon:
        return {"home_wins": 0, "away_wins": 0, "draws": 0,
                "home_gf_avg": 0.0, "summary": "Limited h2h data (0 matches found)"}
    d = (hist[
            ((hist["HomeTeam"] == home_canon) & (hist["AwayTeam"] == away_canon))
            | ((hist["HomeTeam"] == away_canon) & (hist["AwayTeam"] == home_canon))
        ]
        .sort_values("_date", ascending=False)
        .head(H2H_N))
    n = len(d)

    def _winner(row):
        if row["FTR"] == "H":
            return row["HomeTeam"]
        if row["FTR"] == "A":
            return row["AwayTeam"]
        return None

    winners = [_winner(r) for _, r in d.iterrows()]
    home_wins = int(sum(1 for w in winners if w == home_canon))
    away_wins = int(sum(1 for w in winners if w == away_canon))
    draws = int((d["FTR"] == "D").sum())

    hosted = d[d["HomeTeam"] == home_canon]
    home_gf_avg = round(float(hosted["FTHG"].mean()), 1) if len(hosted) else 0.0

    if n < 3:
        summary = f"Limited h2h data ({n} matches found)"
    else:
        summary = f"Home {home_wins}W {draws}D {away_wins}L in last {n} meetings"

    return {"home_wins": home_wins, "away_wins": away_wins, "draws": draws,
            "home_gf_avg": home_gf_avg, "summary": summary}


# --------------------------------------------------------------------------- #
# STEP 6 - model performance
# --------------------------------------------------------------------------- #
def _as_bool(series: pd.Series) -> pd.Series:
    return series.map(lambda v: str(v).strip().lower() in {"true", "1", "1.0", "yes"})


def model_performance() -> dict:
    res = pd.read_csv(RESULTS_CSV)
    res = res[res["FTR"].notna() & (res["FTR"].astype(str).str.strip() != "")]
    # results_merged.csv is written newest-first (merge_results.py sorts desc on
    # generated_at); the "last 30" / "last 5" the spec means are the most recent.
    if "generated_at" in res.columns:
        res = res.sort_values("generated_at", ascending=False)
    res = res.head(PERF_N)

    total = int(len(res))
    if total == 0:
        return {"total_predictions": 0, "overall_accuracy_pct": 0.0,
                "edge_count": 0, "edge_accuracy_pct": 0.0, "edge_profit": 0.0,
                "fade_count": 0, "fade_accuracy_pct": 0.0,
                "streak_label": "MIXED", "streak_string": "", "streak_last5": []}

    correct = _as_bool(res["correct"])
    is_edge = _as_bool(res["is_edge"])
    edge_correct = _as_bool(res["edge_correct"])
    is_fade = _as_bool(res["is_fade"])
    fade_correct = _as_bool(res["fade_correct"])
    profit = pd.to_numeric(res["profit"], errors="coerce").fillna(0.0)

    edge_count = int(is_edge.sum())
    fade_count = int(is_fade.sum())

    streak_recent_first = [bool(x) for x in correct.tolist()[:5]]
    streak_chrono = list(reversed(streak_recent_first))  # most recent rightmost
    hits = sum(1 for x in streak_chrono if x)
    streak_label = "HOT" if hits >= 4 else "COLD" if hits <= 1 else "MIXED"

    return {
        "total_predictions": total,
        "overall_accuracy_pct": round(int(correct.sum()) / total * 100, 1),
        "edge_count": edge_count,
        "edge_accuracy_pct": round(int(edge_correct.sum()) / edge_count * 100, 1) if edge_count else 0.0,
        "edge_profit": round(float(profit[is_edge].sum()), 2),
        "fade_count": fade_count,
        "fade_accuracy_pct": round(int(fade_correct.sum()) / fade_count * 100, 1) if fade_count else 0.0,
        "streak_label": streak_label,
        "streak_string": " ".join("W" if x else "L" for x in streak_chrono),
        "streak_last5": streak_chrono,
    }


# --------------------------------------------------------------------------- #
# STEP 7 - news context
# --------------------------------------------------------------------------- #
def load_news_index() -> list[tuple[str, str, dict]]:
    if not NEWS_JSON.exists():
        return []
    try:
        data = json.loads(NEWS_JSON.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[context] warn: could not read {NEWS_JSON}: {exc}")
        return []
    idx = []
    for nf in data.get("fixtures", []):
        idx.append((_norm(nf.get("home_team", "")), _norm(nf.get("away_team", "")), nf))
    return idx


def match_news(news_index, home: str, away: str) -> dict | None:
    h, a = _norm(home), _norm(away)
    for nh, na, nf in news_index:
        if nh == h and na == a:
            return nf
    keys = [f"{nh}|{na}" for nh, na, _ in news_index]
    cand = difflib.get_close_matches(f"{h}|{a}", keys, n=1, cutoff=0.8)
    if cand:
        return news_index[keys.index(cand[0])][2]
    return None


def top_headlines(entries, k: int = 3) -> list[str]:
    out: list[str] = []
    for e in (entries or [])[:k]:
        if isinstance(e, dict) and e.get("headline"):
            out.append(e["headline"])
        elif isinstance(e, str) and e:
            out.append(e)
    return out


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    now = datetime.now(timezone.utc)
    today = now.date()
    end = today + timedelta(days=LOOKAHEAD_DAYS)

    # ---- STEP 1: upcoming fixtures ------------------------------------------
    pred = pd.read_csv(PREDICTIONS_CSV)
    pred["_kd"] = pd.to_datetime(pred["kickoff_time_utc"], errors="coerce", utc=True)
    pred = pred[pred["_kd"].notna()]
    upcoming = pred[pred["_kd"].dt.date.between(today, end)].copy()

    hist = load_history()
    hometeams = set(hist["HomeTeam"].dropna().astype(str).unique())
    names = pd.unique(
        pd.concat([upcoming["home_team"], upcoming["away_team"]]).astype(str)
    )
    norm_map = build_norm_map(names, hometeams)

    news_index = load_news_index()

    fixtures_out = []
    for _, r in upcoming.iterrows():
        home, away = str(r["home_team"]), str(r["away_team"])
        prob = float(r["prob_homewin"])
        try:
            odds = float(r["odds_B365H"])
        except (TypeError, ValueError):
            odds = None

        signal = "Home" if str(r.get("pred_label")).strip() in {"1", "1.0"} else "Not Home"

        if odds and odds > 0:
            implied = 1.0 / odds
            value_gap = prob - implied
        else:
            implied = value_gap = None

        if signal == "Home" and value_gap is not None:
            edge_label = "EDGE" if value_gap > 0 else "FADE"
        else:
            edge_label = "N/A"

        home_canon = norm_map.get(home)
        away_canon = norm_map.get(away)

        kickoff_str = str(r["kickoff_time_utc"])
        nf = match_news(news_index, home, away)
        if nf:
            nk = nf.get("kickoff")
            if nk and "T" in str(nk) and "T" not in kickoff_str:
                kickoff_str = str(nk)
            home_news = top_headlines(nf.get("home_news"))
            away_news = top_headlines(nf.get("away_news"))
        else:
            home_news = []
            away_news = []

        fixtures_out.append({
            "home_team": home,
            "away_team": away,
            "kickoff": kickoff_str,
            "prob_homewin": round(prob, 3),
            "signal": signal,
            "odds": round(odds, 2) if odds else None,
            "implied_prob": round(implied, 3) if implied is not None else None,
            "value_gap": round(value_gap, 3) if value_gap is not None else None,
            "edge_label": edge_label,
            "home_team_form": team_form(hist, home_canon),
            "away_team_form": team_form(hist, away_canon),
            "h2h": head_to_head(hist, home_canon, away_canon),
            "home_news": home_news,
            "away_news": away_news,
        })

    perf = model_performance()

    payload = {
        "computed_at": now.isoformat(),
        "model_performance": perf,
        "fixtures": fixtures_out,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"[context] computed context for {len(fixtures_out)} fixtures")
    print(f"[context] model: {perf['overall_accuracy_pct']}% accuracy, {perf['streak_label']} streak")
    print(f"[context] wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
