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

FORM_N = 5
H2H_N = 5
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


def compute_league_table(hist: pd.DataFrame) -> list[dict]:
    """Current-season (SEASON_START onwards) league table - one row per
    team with played/won/drawn/lost/goals/points, ordered by position
    (points desc, then goal difference desc, then goals for desc)."""
    season = hist[hist["_date"] >= SEASON_START]
    teams = sorted(set(season["HomeTeam"].dropna()) | set(season["AwayTeam"].dropna()))

    rows = []
    for team in teams:
        team_games = season[(season["HomeTeam"] == team) | (season["AwayTeam"] == team)]
        played = won = drawn = lost = 0
        gf = ga = 0.0
        for _, row in team_games.iterrows():
            res, g_for, g_against = _perspective(row, team)
            played += 1
            gf += g_for
            ga += g_against
            if res == "W":
                won += 1
            elif res == "D":
                drawn += 1
            else:
                lost += 1
        rows.append({
            "team": team,
            "played": played,
            "won": won,
            "drawn": drawn,
            "lost": lost,
            "goals_for": int(round(gf)),
            "goals_against": int(round(ga)),
            "goal_difference": int(round(gf - ga)),
            "points": won * 3 + drawn,
        })

    rows.sort(key=lambda r: (-r["points"], -r["goal_difference"], -r["goals_for"], r["team"]))

    table = []
    for i, row in enumerate(rows, start=1):
        table.append({"position": i, **row})
    return table


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
    # Use ALL scored rows - matches generate_github_pages.py's Performance
    # Tracker section exactly (it reads the full CSV with no row-count
    # window), so the two numbers shown on the page never disagree.
    # results_merged.csv is written newest-first (merge_results.py sorts desc
    # on generated_at); "last 5" for the streak means the most recent 5.
    if "generated_at" in res.columns:
        res = res.sort_values("generated_at", ascending=False)

    total = int(len(res))
    if total == 0:
        return {"total_predictions": 0, "avoid_count": 0, "overall_accuracy_pct": 0.0,
                "edge_count": 0, "edge_accuracy_pct": 0.0, "edge_profit": 0.0,
                "fade_count": 0, "fade_accuracy_pct": 0.0,
                "streak_label": "MIXED", "streak_string": "", "streak_last5": []}

    # Match the page's performance tracker: accuracy is over CONFIDENT
    # predictions only - "Avoid" rows are excluded (counted separately).
    pred_col = res["prediction"] if "prediction" in res.columns else res.get("pred_label", "")
    is_avoid = pred_col.astype(str).str.strip().str.lower() == "avoid"
    avoid_count = int(is_avoid.sum())
    confident = res[~is_avoid]
    n_confident = int(len(confident))

    correct = _as_bool(res["correct"])              # full window - used for streak
    correct_conf = _as_bool(confident["correct"])   # confident only - used for accuracy
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
        "total_predictions": n_confident,
        "avoid_count": avoid_count,
        "overall_accuracy_pct": round(int(correct_conf.sum()) / n_confident * 100, 1) if n_confident else 0.0,
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


# Headline phrases indicating a player is FIT, not injured - a headline
# containing any of these is not an injury concern and must be excluded at
# source so it never reaches the GPT prompt. Deliberately does NOT include
# "returns to training" - that phrase also shows up in genuine injury
# updates (e.g. "X returns to training after three weeks out").
FIT_PLAYER_PHRASES = [
    "is fit", "fit and available", "no injury", "back in training",
    "cleared to play", "available for selection", "passed fit",
    "fitness boost", "back from injury", "returns from injury",
]


# Status keywords an injury headline gets classified into, checked in this
# order so a more specific phrase ("ruled out") wins over a bare "out".
_STATUS_PATTERNS = [
    (re.compile(r"\bruled out\b"), "ruled out"),
    (re.compile(r"\bmisses?\b"), "misses"),
    (re.compile(r"\bdoubtful\b"), "doubtful"),
    (re.compile(r"\bdoubt\b"), "doubtful"),
    (re.compile(r"\bunavailable\b"), "unavailable"),
    (re.compile(r"\binjury concern\b"), "injury concern"),
    (re.compile(r"\bout\b"), "out"),
]

_NAME_RE = re.compile(r"\b([A-Z][a-z']+(?:[-’ ][A-Z][a-z']+)+)\b")

# Headline "furniture" words that capitalise at the start of a sentence and
# would otherwise be mistaken for a player's first name (e.g. "Injured
# Sessegnon could miss...").
_GENERIC_LEAD_WORDS = {
    "injured", "confirmed", "exclusive", "breaking", "official",
    "report", "reports", "revealed", "update", "latest", "news", "team",
    "watch", "video", "live", "gallery", "analysis", "opinion",
    "should", "why", "how", "when", "what", "who", "will", "can",
    "does", "did", "has", "have", "could", "would", "big", "huge",
    "major", "shock", "surprise", "early", "triple", "controversial",
}

_GENERIC_TRAIL_WORDS = {
    "injury", "injuries", "update", "updates", "news", "latest",
    "report", "reports", "watch", "video", "live",
}

_COMPETITION_STOP_PHRASES = {
    "champions league", "premier league", "europa league", "carabao cup",
    "fa cup", "nations league", "world cup", "super cup", "efl cup",
}

# Current Premier League stadium/venue names - these read exactly like a
# plausible "Firstname Lastname" candidate to the name regex but are never
# a player.
_VENUE_STOP_PHRASES = {
    "elland road", "emirates stadium", "etihad stadium", "old trafford",
    "stamford bridge", "london stadium", "villa park", "molineux stadium",
    "selhurst park", "craven cottage", "vitality stadium", "goodison park",
    "the city ground", "portman road", "bramall lane", "turf moor",
    "st james", "st mary", "tottenham hotspur stadium",
}

# "Home nations" international sides - frequently the first capitalised
# 2-word phrase in headlines about a player away on international duty
# (e.g. "Northern Ireland boss responds to Conor Bradley injury update").
# Not an exhaustive list of countries - a foreign nation not on this list
# is a known gap in this best-effort extractor.
_NATION_STOP_PHRASES = {
    "northern ireland", "republic of ireland", "england", "scotland", "wales",
}


def extract_injury_headline(headline: str, team_names: set[str]) -> str | None:
    """Best-effort 'Firstname Lastname — status' extraction from a raw
    injury headline (pure Python, no AI). Returns None when no clean
    player + status pair can be found - the caller should then drop the
    headline entirely rather than pass through a truncated or irrelevant
    one."""
    low = headline.lower()

    status = None
    for pattern, label in _STATUS_PATTERNS:
        if pattern.search(low):
            status = label
            break
    if status is None:
        if "injury" in low:
            status = "injury concern"
        else:
            return None

    stop = ({t.lower() for t in team_names} | _COMPETITION_STOP_PHRASES
            | _VENUE_STOP_PHRASES | _NATION_STOP_PHRASES)

    name = None
    for m in _NAME_RE.finditer(headline):
        words = m.group(1).split()
        # Strip leading headline "furniture" words (e.g. "Should Erling
        # Haaland's ..." -> "Erling Haaland's", "Injured Sessegnon ..." ->
        # just "Sessegnon", which then fails the 2-word minimum and is
        # correctly skipped) so a real name isn't rejected just because a
        # question/lead word happened to precede it in the same capitalised
        # run.
        while len(words) > 2 and words[0].lower() in _GENERIC_LEAD_WORDS:
            words = words[1:]
        # Same idea for trailing "furniture" words (e.g. "Anthony Elanga
        # Injury Update" -> "Anthony Elanga").
        while len(words) > 2 and words[-1].lower() in _GENERIC_TRAIL_WORDS:
            words = words[:-1]
        if (len(words) < 2 or words[0].lower() in _GENERIC_LEAD_WORDS
                or words[-1].lower() in _GENERIC_TRAIL_WORDS):
            continue
        # A real name is 2-3 words - a long title-case run swept up whole
        # (e.g. "Blow Leaves Both Sides Facing Early Problems") is never a
        # plausible name, no matter what its individual words are.
        if len(words) > 3:
            continue
        cand = " ".join(words)
        # Strip a trailing possessive ("Haaland's" -> "Haaland") for a
        # clean player name.
        if cand.endswith("’s") or cand.endswith("'s"):
            cand = cand[:-2]
        cl = cand.lower()
        # Reject if the candidate contains a known team name, competition
        # or stadium anywhere within it, not just an exact match - catches
        # cases like "Triple Newcastle" or "Chelsea Injury News" where a
        # real team name got swept up alongside an adjacent capitalised word.
        if any(stop_phrase in cl for stop_phrase in stop):
            continue
        # skip a speaker/journalist/manager reporting the news, rather than
        # the player it's about ("Adam Pope reveals...", "X drops update...")
        after = headline[m.end():m.end() + 30].lower()
        if re.match(r"\s+(provides?|says?|reveals?|confirms?|gives?|"
                    r"explains?|admits?|addresses|hopes?|expects?|laments?|"
                    r"drops?|issues?|delivers?|shares?|offers?|makes?|"
                    r"sends?|writes?|claims?|insists?|warns?|reacts?|"
                    r"responds?)\b", after):
            continue
        name = cand
        break

    if not name:
        return None

    return f"{name} — {status}"


def top_headlines(entries, team_names: set[str], k: int = 3) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for e in (entries or []):
        if isinstance(e, dict) and e.get("headline"):
            headline = e["headline"]
        elif isinstance(e, str) and e:
            headline = e
        else:
            continue
        low = headline.lower()
        if any(phrase in low for phrase in FIT_PLAYER_PHRASES):
            continue  # player is fit, not an injury concern - exclude
        extracted = extract_injury_headline(headline, team_names)
        if extracted is None:
            continue  # no clean player+status extraction - skip entirely
        name_part = extracted.split(" — ")[0].lower()
        if name_part in seen:
            continue  # multiple headlines about the same player - dedupe
        seen.add(name_part)
        out.append(extracted)
        if len(out) >= k:
            break
    return out


def get_gameweek_window(now: datetime) -> tuple:
    """
    Returns (start, end) datetime range for the current
    or next gameweek.

    Gameweek = Friday 00:00 to Monday 23:59 UTC.

    If today is Fri/Sat/Sun/Mon: use this week's window.
    If today is Tue/Wed/Thu: use next Friday to Monday.
    """
    weekday = now.weekday()  # Mon=0, Fri=4, Sun=6

    if weekday == 4:   # Friday
        days_to_friday = 0
    elif weekday == 5:  # Saturday
        days_to_friday = -1
    elif weekday == 6:  # Sunday
        days_to_friday = -2
    elif weekday == 0:  # Monday
        days_to_friday = -3
    else:               # Tue/Wed/Thu — look ahead to next Friday
        days_to_friday = (4 - weekday) % 7

    friday = (now + timedelta(days=days_to_friday)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    monday = friday + timedelta(days=3, hours=23, minutes=59)

    return friday, monday


def betting_category(prob: float) -> str:
    """Pre-computed betting bucket from the home-win probability (pure Python)."""
    if prob >= 0.55:
        return "back_home"
    if prob >= 0.45:
        return "avoid"
    if prob >= 0.20:
        return "double_chance"
    return "strong_fade"


def confidence_label(cat: str, prob: float) -> str:
    """Pre-computed confidence label from betting_category + prob_homewin
    (pure Python)."""
    if cat == "back_home" and prob >= 0.70:
        return "High"
    if cat == "strong_fade" and prob <= 0.15:
        return "High"
    if cat == "double_chance":
        return "Medium"
    if cat == "back_home" and 0.55 <= prob < 0.70:
        return "Medium"
    return "Low"


def double_chance_direction(cat: str) -> str:
    """Pre-computed away/draw direction text for double_chance fixtures."""
    return "Back Away Win or Draw (X2)" if cat == "double_chance" else ""


def bet_description(cat: str) -> str:
    """Pre-computed human-readable bet description from betting_category."""
    return {
        "back_home": "Back Home to Win",
        "double_chance": "Back Away Win or Draw (X2)",
        "strong_fade": "Back Away Win",
        "avoid": "Skip — too close to call",
    }.get(cat, "")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    now = datetime.now(timezone.utc)
    gameweek_start, gameweek_end = get_gameweek_window(now)

    # ---- STEP 1: upcoming fixtures ------------------------------------------
    pred = pd.read_csv(PREDICTIONS_CSV)
    pred["_kd"] = pd.to_datetime(pred["kickoff_time_utc"], errors="coerce", utc=True)
    pred = pred[pred["_kd"].notna()]
    upcoming = pred[
        (pred["_kd"] >= gameweek_start) & (pred["_kd"] <= gameweek_end)
    ].copy()
    upcoming = upcoming[upcoming["_kd"] > now - timedelta(minutes=5)]

    if upcoming.empty:
        print("[context] No fixtures in current gameweek window")
        print(f"[context] Window: {gameweek_start.date()} to {gameweek_end.date()}")
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(
            json.dumps(
                {
                    "computed_at": now.isoformat(),
                    "gameweek_start": gameweek_start.isoformat(),
                    "gameweek_end": gameweek_end.isoformat(),
                    "model_performance": model_performance(),
                    "fixtures": [],
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"[context] wrote empty context to {OUT_JSON}")
        exit(0)

    hist = load_history()
    hometeams = set(hist["HomeTeam"].dropna().astype(str).unique())
    names = pd.unique(
        pd.concat([upcoming["home_team"], upcoming["away_team"]]).astype(str)
    )
    norm_map = build_norm_map(names, hometeams)

    known_team_names = set(hometeams)
    for key, variants in KNOWN_VARIANTS.items():
        known_team_names.add(key)
        known_team_names.update(variants)

    league_table = compute_league_table(hist)
    league_position_by_team = {row["team"]: row["position"] for row in league_table}

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
            home_news = top_headlines(nf.get("home_news"), known_team_names)
            away_news = top_headlines(nf.get("away_news"), known_team_names)
        else:
            home_news = []
            away_news = []

        cat = betting_category(prob)

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
            "betting_category": cat,
            "confidence": confidence_label(cat, prob),
            "double_chance_direction": double_chance_direction(cat),
            "bet_description": bet_description(cat),
            "is_strong_fade": bool(prob < 0.20),
            "home_team_form": team_form(hist, home_canon),
            "away_team_form": team_form(hist, away_canon),
            "h2h": head_to_head(hist, home_canon, away_canon),
            "home_league_position": league_position_by_team.get(home_canon),
            "away_league_position": league_position_by_team.get(away_canon),
            "home_news": home_news,
            "away_news": away_news,
        })

    perf = model_performance()

    payload = {
        "computed_at": now.isoformat(),
        "gameweek_start": gameweek_start.isoformat(),
        "gameweek_end": gameweek_end.isoformat(),
        "model_performance": perf,
        "league_table": league_table,
        "fixtures": fixtures_out,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"[context] gameweek window: {gameweek_start.date()} to {gameweek_end.date()}")
    for fx in fixtures_out:
        print(f"[context]   {fx['home_team']} vs {fx['away_team']} — {fx['kickoff']}")
    print(f"[context] computed context for {len(fixtures_out)} fixtures")
    print(f"[context] model: {perf['overall_accuracy_pct']}% accuracy, {perf['streak_label']} streak")
    print(f"[context] wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
