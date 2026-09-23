#!/usr/bin/env python3
"""Generate the AI pundit betting strategy from pre-computed match context.

Reads ``artifacts/match_context.json`` ONLY - no raw data, no maths. Retrieves
similar past fixtures from the scored strategy archive (RAG), asks GPT-4o-mini
once for an opinionated pundit strategy, then writes:

  artifacts/strategy_latest.json
  artifacts/strategy_latest.md
  artifacts/strategy_archive/strategy_<timestamp>.json   (scored: false)
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, field_validator
from typing import Literal

import compute_context


class FixtureStrategy(BaseModel):
    home_team: str
    away_team: str
    kickoff: str
    signal: Literal["Home", "Not Home", "Avoid"]
    confidence: Literal["High", "Medium", "Low"]
    edge_label: Literal["EDGE", "FADE", "N/A"]
    prob_homewin: float = 0.0
    odds: float = 0.0
    value_gap: float = 0.0
    pundit_take: str
    bet_type: str
    stake_advice: str
    pundit_action: str
    betting_category: str = ""
    rag_informed: bool = False

    @field_validator("prob_homewin", "value_gap", mode="before")
    @classmethod
    def normalise_percentage(cls, v):
        v = float(v)
        if abs(v) > 1:
            v = v / 100
        # hard clamp to catch any remaining outliers (pos or neg)
        v = max(-1.0, min(1.0, v))
        return round(v, 4)

    @field_validator("edge_label", mode="before")
    @classmethod
    def normalise_edge(cls, v):
        return str(v).upper() if v else "N/A"


class WeekendStrategy(BaseModel):
    generated_at: str
    model_form: str
    gameweek_summary: str
    rest_of_card_paragraph: str = ""
    top_picks: list[FixtureStrategy]
    fixtures_full: list[FixtureStrategy]
    strong_fades: list[FixtureStrategy] = []
    double_chances: list[FixtureStrategy] = []
    avoid_list: list[FixtureStrategy] = []
    value_bets: list[FixtureStrategy] = []


# Resolve forward refs (module uses `from __future__ import annotations`)
WeekendStrategy.model_rebuild()

CONTEXT_JSON = Path("artifacts/match_context.json")
ARCHIVE_DIR = Path("artifacts/strategy_archive")

# Early testing snapshots from before regular gameweek numbering started -
# the only RAG history that predates it, so clean_strategy_archive() must
# never sweep them up even though get_gameweek_window() groups them with a
# later, already-thinned gameweek.
PROTECTED_ARCHIVE_FILES = {"strategy_20260911T230002Z.json"}
LATEST_JSON = Path("artifacts/strategy_latest.json")
LATEST_MD = Path("artifacts/strategy_latest.md")
FAISS_INDEX = Path("artifacts/strategy_faiss.index")

# Only read in no-fixtures mode, to work out when predictions resume and to
# build the pundit's lookback review of the gameweek just gone.
PREDICTIONS_CSV = Path("snapshots/predictions_latest.csv")
RESULTS_CSV = Path("data/processed/results_merged.csv")
LOOKBACK_RESULTS_N = 10

MODEL = "gpt-4o-mini"
EMBED_MODEL = "text-embedding-3-small"
# The schema repeats full fixture objects across fixtures_full + top_picks +
# value_bets + avoid_list, so a full gameweek needs well over 2500 tokens or the
# JSON comes back truncated mid-object. gpt-4o-mini allows up to 16384.
MAX_TOKENS = 8000
FAISS_MIN_SCORED = 20

SYSTEM_PROMPT = (
    "You are a world-class football pundit and professional sports bettor with "
    "20 years of Premier League experience. You combine statistical modelling "
    "with qualitative insight. You give direct, opinionated, actionable betting "
    "advice. You commit to picks and explain why. You speak like a confident "
    "expert, not a disclaimer-heavy robot.\n\n"
    "Rules you must follow:\n"
    "- When model is HOT back it hard on clear signals\n"
    "- When model is COLD only take the very clearest value\n"
    "- EDGE means the model sees more value than the market\n"
    "- Banker = High confidence Home + EDGE + good form + clean injury news\n"
    "- Never call a short-odds favourite a value bet - that is stake "
    "management only\n"
    "- If RAG shows the model was wrong in similar past situations acknowledge "
    "it and reduce confidence\n"
    "- Write pundit_take as natural spoken pundit language\n"
    "- Do not compute probabilities yourself - use only the pre-computed "
    "values in the data.\n\n"
    "BETTING CATEGORIES\n"
    "Use the pre-computed betting_category field for each fixture - do not "
    "override it with your own calculation:\n"
    "- back_home: recommend backing the home team\n"
    "- avoid: genuinely too close to call, skip entirely\n"
    "- double_chance: recommend double chance (draw or away)\n"
    "- strong_fade: recommend backing the away team to win\n"
    "For pundit_action use exactly:\n"
    "- back_home: 'Back Home (Banker)' or 'Back Home (Value)'\n"
    "- avoid: 'Skip \u2014 too close to call'\n"
    "- double_chance: 'Back Double Chance (X2)'\n"
    "- strong_fade: 'Strong Fade \u2014 Back Away Win'\n"
    "For strong_fade fixtures: bet_type must be 'Back Away Win', "
    "stake_advice must be 'Small', pundit_action must be "
    "'Strong Fade \u2014 Back Away Win'.\n"
    "For double_chance fixtures: stake_advice must be 'Small'. Never "
    "use 'Skip' as stake_advice for double_chance fixtures - Skip is "
    "only for avoid fixtures.\n\n"
    "RESPECT THE PRE-COMPUTED CATEGORY IN FREE TEXT\n"
    "In rest_of_card_paragraph and pundit_take you MUST respect the "
    "pre-computed betting_category for each fixture:\n"
    "- double_chance fixtures must be described as double chance bets - "
    "never as avoid or skip\n"
    "- strong_fade fixtures must be described as back away win\n"
    "- avoid fixtures are the only ones to describe as skip\n"
    "The betting_category is pre-computed by the model in Python. You are "
    "not permitted to override it with your own assessment. Your job is "
    "to explain WHY the category makes sense, not to reassign it.\n\n"
    "OUTPUT ARRAYS\n"
    "Populate these arrays in your response:\n"
    "- top_picks: all fixtures where betting_category==back_home\n"
    "- strong_fades: all fixtures where betting_category==strong_fade\n"
    "- double_chances: all fixtures where betting_category==double_chance\n"
    "- avoid_list: all fixtures where betting_category==avoid\n"
    "Also populate fixtures_full with every fixture.\n\n"
    "TOP PICKS RANKING\n"
    "Within top_picks rank fixtures by conviction - the fixture with the "
    "highest prob_homewin AND positive or neutral value_gap should be "
    "stake_advice Banker. Others are Value Bet or Small based on your "
    "analysis of form, injuries and value. You may use injury news and "
    "form data to justify why a lower probability fixture deserves Banker "
    "over a higher probability one.\n\n"
    "EDGE/FADE BADGES ARE INDEPENDENT\n"
    "The edge_label field (EDGE/FADE/N/A) is pre-computed and independent of "
    "betting_category. Keep edge_label exactly as provided - do not change it. "
    "A strong_fade fixture can also be EDGE if the away odds offer value.\n\n"
    "INJURY NEWS\n"
    "You MUST reference specific named injuries in pundit_take where home_news "
    "or away_news headlines mention a player injury. Extract the player name "
    "and injury from the headline and include it naturally in your pundit "
    "analysis. If no injury headlines exist for a team, do not mention "
    "injuries for that team. Never write generic injury disclaimers.\n\n"
    "LEAGUE TABLE\n"
    "The current season's league table is provided in the context - each "
    "fixture includes home_league_position and away_league_position, "
    "pre-computed from that table. Use these league positions accurately "
    "in pundit_take when relevant to your analysis (e.g. a top-of-the-table "
    "team hosting a relegation-threatened side). Do NOT invent or estimate "
    "league positions - only use the league_table data provided in the "
    "context.\n\n"
    "GAMEWEEK SUMMARY\n"
    "gameweek_summary must name specific teams and facts. Mention: the "
    "standout value bet by name, and one specific named injury if any "
    "exists in the news data. Mention the biggest mismatch from the "
    "REMAINING fixtures only - do not reference games that have already "
    "kicked off. No generic statements.\n\n"
    "REST OF THE CARD PARAGRAPH\n"
    "Generate a field called rest_of_card_paragraph. This is a pundit's "
    "summary paragraph covering the strong fades, double chance and avoid "
    "fixtures.\n"
    "Rules:\n"
    "- Write in natural pundit voice - opinionated, direct\n"
    "- Describe each fixture qualitatively using the pre-computed "
    "betting_category and form/h2h data - never invent or write out numeric "
    "figures\n"
    "- Reference specific betting_category thresholds in words, not "
    "numbers: strong_fade = well below a coin-flip on the home win; "
    "double_chance = below-average but not hopeless home win chances; "
    "avoid = too close to call\n"
    "- Reference specific injury news from home_news and away_news where "
    "relevant - name the player\n"
    "- You MUST reference the model's recent performance using the "
    "streak_label word (e.g. HOT) and a qualitative sense of its accuracy "
    "(e.g. 'in strong form') - do not write out the accuracy number\n"
    "- Reference h2h or form data where it strengthens the argument\n"
    "- Do NOT use phrases like 'keep an eye on' or generic disclaimers\n"
    "- Structure naturally: start with strong fades, move to double "
    "chances, end with avoids\n"
    "- Keep it under 120 words\n"
    "- Sound like a pundit who has studied the numbers and the news, not a "
    "robot reading a spreadsheet\n"
    "Example tone (do not copy this exactly - use real data from this "
    "week): 'The Manchester derby is as close to a no-bet as it gets for "
    "the home side - United look out of their depth here which is a "
    "signal to back City all day. Similarly Sunderland hosting Arsenal "
    "is a strong fade. For those looking at double chances, Villa "
    "against Forest is interesting but Goretzka's knee injury weakens "
    "their midfield and the h2h favours a tight game. Leeds vs "
    "Newcastle is another one to take double chance rather than back "
    "the home side. The model is currently HOT and in strong form - "
    "trust the signals this week.'\n\n"
    "CRITICAL RULE: Never write percentage figures, probability numbers, "
    "or odds figures in pundit_take, rest_of_card_paragraph or "
    "gameweek_summary. Do not write things like '93%', '28.1%', '1.24 "
    "odds'. Describe form and situation in words only.\n"
    "Example of WRONG: 'Chelsea have a 93% chance of winning'\n"
    "Example of RIGHT: 'Chelsea are overwhelming favourites and should "
    "have too much quality for Hull City'\n"
    "The structured fields (prob_homewin, odds, value_gap) already show "
    "the numbers - your job is to add qualitative insight not repeat the "
    "numbers."
)

FIXTURE_SCHEMA = """{
  "home_team": "...",
  "away_team": "...",
  "kickoff": "...",
  "signal": "Home|Not Home|Avoid",
  "confidence": "High|Medium|Low",
  "edge_label": "EDGE|FADE|N/A",
  "betting_category": "back_home|avoid|double_chance|strong_fade (PRE-COMPUTED, keep exactly)",
  "is_strong_fade": true/false,
  "pundit_take": "2-3 sentence analysis",
  "pundit_action": "determined by betting_category EXACTLY: back_home -> 'Back Home (Banker)' or 'Back Home (Value)'; avoid -> 'Skip \u2014 too close to call'; double_chance -> 'Back Double Chance (X2)'; strong_fade -> 'Strong Fade \u2014 Back Away Win'",
  "bet_type": "Back Home|Lay Home|Skip",
  "stake_advice": "Banker|Value Bet|Small|Skip",
  "rag_informed": true/false
}"""

def build_output_schema(include_rest_of_card: bool) -> str:
    """The JSON schema shown to GPT. rest_of_card_paragraph is only included
    when there are enough remaining fixtures (>=2) for a "rest of the card"
    summary to mean anything - with 0 or 1 remaining fixtures the pundit
    just analyses that fixture directly."""
    rest_of_card_line = (
        '  "rest_of_card_paragraph": "single flowing pundit paragraph '
        '(<120 words) covering strong fades, double chances then avoids, '
        'using qualitative descriptions of form/situation (no percentage '
        'or odds figures) and named injury news",\n'
        if include_rest_of_card else ""
    )
    return (
        "{\n"
        '  "generated_at": "ISO datetime",\n'
        '  "model_form": "one sentence on recent model form",\n'
        '  "gameweek_summary": "2-3 sentence pundit overview",\n'
        f"{rest_of_card_line}"
        '  "top_picks": [...all betting_category==back_home fixture objects...],\n'
        '  "strong_fades": [...all betting_category==strong_fade fixture objects...],\n'
        '  "double_chances": [...all betting_category==double_chance fixture objects...],\n'
        '  "avoid_list": [...all betting_category==avoid fixture objects...],\n'
        '  "fixtures_full": [...ALL fixture objects...],\n'
        '  "value_bets": [...EDGE fixtures only...]\n'
        "}"
    )


# --------------------------------------------------------------------------- #
# STEP 1 - RAG retrieval
# --------------------------------------------------------------------------- #
def load_scored_archive() -> list[dict]:
    out = []
    for path in sorted(glob.glob(str(ARCHIVE_DIR / "*.json"))):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("scored") is True:
            data["_path"] = path
            out.append(data)
    return out


def collect_past_fixtures(archives: list[dict]) -> list[dict]:
    rows = []
    for arch in archives:
        arch_date = str(arch.get("generated_at", ""))[:10]
        for fx in arch.get("fixtures_full", []):
            fx = dict(fx)
            fx.setdefault("_date", str(fx.get("kickoff", ""))[:10] or arch_date)
            rows.append(fx)
    return rows


def similarity(cur: dict, past: dict) -> int:
    score = 0
    if cur.get("home_team") and cur.get("home_team") == past.get("home_team"):
        score += 2
    if cur.get("away_team") and cur.get("away_team") == past.get("away_team"):
        score += 2
    try:
        if abs(float(cur.get("prob_homewin", 0)) - float(past.get("prob_homewin", 0))) <= 0.10:
            score += 3
    except (TypeError, ValueError):
        pass
    if cur.get("signal") and cur.get("signal") == past.get("signal"):
        score += 2
    if cur.get("edge_label") and cur.get("edge_label") == past.get("edge_label"):
        score += 1
    return score


def maybe_build_faiss(past_fixtures: list[dict], n_scored: int):
    """Build + persist a FAISS index when the archive is large enough.

    Returns a callable pool-filter (cur -> list[past]) or None to use the
    full pool. Best-effort: any failure falls back to the heuristic pool.
    """
    if n_scored <= FAISS_MIN_SCORED:
        return None
    try:
        import faiss  # type: ignore
        import numpy as np

        client = _openai_client()
        texts = [
            f"{f.get('home_team')} vs {f.get('away_team')} "
            f"prob={float(f.get('prob_homewin', 0)):.2f} "
            f"signal={f.get('signal')} edge={f.get('edge_label')}"
            for f in past_fixtures
        ]
        if not texts:
            return None
        vecs = client.embeddings.create(model=EMBED_MODEL, input=texts)
        mat = np.array([d.embedding for d in vecs.data], dtype="float32")
        faiss.normalize_L2(mat)
        index = faiss.IndexFlatIP(mat.shape[1])
        index.add(mat)
        FAISS_INDEX.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(FAISS_INDEX))

        def _filter(cur: dict) -> list[dict]:
            q = (
                f"{cur.get('home_team')} vs {cur.get('away_team')} "
                f"prob={float(cur.get('prob_homewin', 0)):.2f} "
                f"signal={cur.get('signal')} edge={cur.get('edge_label')}"
            )
            qv = client.embeddings.create(model=EMBED_MODEL, input=[q])
            qm = np.array([qv.data[0].embedding], dtype="float32")
            faiss.normalize_L2(qm)
            _, idx = index.search(qm, min(10, len(past_fixtures)))
            return [past_fixtures[i] for i in idx[0] if 0 <= i < len(past_fixtures)]

        return _filter
    except Exception as exc:  # noqa: BLE001
        print(f"[strategy] FAISS unavailable, using heuristic RAG only: {exc}")
        return None


def build_rag_context(cur: dict, past_fixtures: list[dict], pool_filter) -> tuple[str, int]:
    if not past_fixtures:
        return "First run - no historical data yet", 0
    pool = pool_filter(cur) if pool_filter else past_fixtures
    ranked = sorted(pool, key=lambda p: similarity(cur, p), reverse=True)
    top = [p for p in ranked if similarity(cur, p) > 0][:3]
    if not top:
        return "First run - no historical data yet", 0
    lines = []
    for p in top:
        take = str(p.get("pundit_take", ""))[:80]
        try:
            prob = float(p.get("prob_homewin", 0))
        except (TypeError, ValueError):
            prob = 0.0
        try:
            profit = float(p.get("profit", 0))
        except (TypeError, ValueError):
            profit = 0.0
        outcome = "correct" if p.get("correct") else "wrong"
        lines.append(
            f"Similar past: {p.get('home_team')} vs {p.get('away_team')} "
            f"({p.get('_date', '')}) - model said {p.get('signal')} at {prob:.0%} - "
            f"pundit said: '{take}...' - outcome: {outcome}, profit: {profit:+.2f} units"
        )
    return "\n".join(lines), len(top)


# --------------------------------------------------------------------------- #
# STEP 2 - build the GPT prompt
# --------------------------------------------------------------------------- #
def fixture_block(fx: dict, rag_context: str) -> str:
    hf = fx.get("home_team_form", {})
    af = fx.get("away_team_form", {})
    h2h = fx.get("h2h", {})
    home_news = fx.get("home_news") or []
    away_news = fx.get("away_news") or []
    prob = float(fx.get("prob_homewin", 0) or 0)
    implied = fx.get("implied_prob")
    implied = float(implied) if implied is not None else 0.0
    gap = fx.get("value_gap")
    gap = float(gap) if gap is not None else 0.0
    return (
        "---\n"
        f"FIXTURE: {fx.get('home_team')} vs {fx.get('away_team')}\n"
        f"Kickoff: {fx.get('kickoff')}\n"
        f"Model: {fx.get('signal')} | Prob home win: {prob:.1%}\n"
        f"Odds: {fx.get('odds')} (market implies {implied:.1%})\n"
        f"Value gap: {gap:+.1%} | {fx.get('edge_label')}\n"
        f"betting_category: {fx.get('betting_category')}\n"
        f"is_strong_fade: {str(bool(fx.get('is_strong_fade'))).lower()}\n"
        f"Home league position: {fx.get('home_league_position', 'N/A')}\n"
        f"Away league position: {fx.get('away_league_position', 'N/A')}\n"
        f"Home season so far: {hf.get('current_season_pts', 0)} pts from "
        f"{hf.get('current_season_games', 0)} games\n"
        f"Home form last 5: {hf.get('form_string', '')} "
        f"({hf.get('pts_last5', 0)} pts, {hf.get('gf_last5', 0)} GF, {hf.get('ga_last5', 0)} GA)\n"
        f"Away season so far: {af.get('current_season_pts', 0)} pts from "
        f"{af.get('current_season_games', 0)} games\n"
        f"Away form last 5: {af.get('form_string', '')} "
        f"({af.get('pts_last5', 0)} pts, {af.get('gf_last5', 0)} GF, {af.get('ga_last5', 0)} GA)\n"
        f"H2H: {h2h.get('summary', '')}\n"
        f"Home news: {' | '.join(home_news) if home_news else 'None'}\n"
        f"Away news: {' | '.join(away_news) if away_news else 'None'}\n"
        f"Historical context: {rag_context}\n"
        "---"
    )


def _parse_kickoff(value) -> datetime | None:
    """Best-effort parse of a fixture's kickoff string to an aware UTC
    datetime. Returns None if it can't be parsed (caller should then treat
    the fixture as unverifiable rather than trust it)."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def get_earlier_gameweek_context(context: dict) -> str:
    """Surface picks made earlier THIS gameweek whose games have since
    kicked off (no longer present in the fresh match_context.json), so the
    pundit can acknowledge them instead of ignoring that part of the card.

    Uses the same Friday-Monday gameweek window as compute_context.py to
    decide which archived runs count as "earlier this gameweek".
    """
    now = datetime.now(timezone.utc)
    gw_start, gw_end = compute_context.get_gameweek_window(now)

    current_keys = {
        f"{fx.get('home_team')}|{fx.get('away_team')}"
        for fx in context.get("fixtures", [])
    }

    earlier_by_key: dict[str, dict] = {}
    for path in sorted(glob.glob(str(ARCHIVE_DIR / "strategy_*.json"))):
        ts_str = Path(path).stem.removeprefix("strategy_")
        try:
            archived_at = datetime.strptime(ts_str, "%Y%m%dT%H%M%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue
        if not (gw_start <= archived_at <= gw_end):
            continue
        try:
            arch = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            continue
        for fx in arch.get("fixtures_full", []) or []:
            key = f"{fx.get('home_team')}|{fx.get('away_team')}"
            earlier_by_key[key] = fx  # later archives win over earlier ones

    kicked_off = []
    for key, fx in earlier_by_key.items():
        if key in current_keys:
            continue
        # Defensive check: only trust this fixture if its own kickoff date
        # actually falls inside the current gameweek window - guards against
        # stale/unrelated fixtures leaking in from an old or malformed
        # archive file.
        kickoff_dt = _parse_kickoff(fx.get("kickoff"))
        if kickoff_dt is None or not (gw_start <= kickoff_dt <= gw_end):
            continue
        kicked_off.append(fx)
    if not kicked_off:
        return ""

    lines = ["Earlier this gameweek the following predictions were made:"]
    for fx in kicked_off:
        action = fx.get("pundit_action", "")
        odds = fx.get("odds")
        odds_part = f" @ {odds}" if odds else ""
        lines.append(
            f"- {fx.get('home_team')} vs {fx.get('away_team')}: {action}"
            f"{odds_part} — game has now kicked off"
        )
    return "\n".join(lines)


def build_user_prompt(context: dict, rag_by_fixture: list[str]) -> str:
    perf = context.get("model_performance", {})
    blocks = [
        fixture_block(fx, rag_by_fixture[i])
        for i, fx in enumerate(context.get("fixtures", []))
    ]
    perf_block = (
        "Model performance context (use these exact figures):\n"
        f"Overall accuracy over the last {perf.get('total_predictions', 0)} "
        f"confident predictions: {perf.get('overall_accuracy_pct')}%\n"
        f"EDGE accuracy: {perf.get('edge_accuracy_pct')}% "
        f"({perf.get('edge_profit', 0):+.2f} units profit)\n"
        f"Current streak: {perf.get('streak_label')} ({perf.get('streak_string')})"
    )
    earlier_context = get_earlier_gameweek_context(context)
    earlier_block = f"Earlier gameweek context: {earlier_context}"

    fixtures = context.get("fixtures", [])
    include_rest_of_card = len(fixtures) >= 2
    if include_rest_of_card:
        rest_of_card_instruction = (
            "rest_of_card_paragraph covers ONLY these specific fixtures: "
            + ", ".join(f"{fx.get('home_team')} vs {fx.get('away_team')}" for fx in fixtures)
            + ". Do not mention any other teams or games."
        )
    else:
        rest_of_card_instruction = (
            "Do NOT include a rest_of_card_paragraph field in your JSON "
            "output at all - there are not enough remaining fixtures this "
            "run for a 'rest of the card' summary. Just analyse the "
            "fixture(s) directly."
        )

    instruction = (
        "Return ONLY valid JSON, no markdown fences, this schema:\n"
        f"{build_output_schema(include_rest_of_card)}\n\n"
        f"Each fixture object:\n{FIXTURE_SCHEMA}\n\n"
        "EVERY fixture object in EVERY array (top_picks, strong_fades, "
        "double_chances, avoid_list, fixtures_full) MUST include every field in "
        "the schema above, including betting_category, pundit_take and "
        "pundit_action. fixtures_full MUST contain ALL fixtures. Assign each "
        "fixture to exactly one of top_picks / strong_fades / double_chances / "
        "avoid_list according to its pre-computed betting_category. "
        "Do NOT include a telegram_message field - it is built separately. "
        "Do NOT include prob_homewin, odds or value_gap on any fixture "
        "object - these are filled in separately from pre-computed data "
        "in Python, not by you. "
        "You have been provided with context about fixtures that were "
        "predicted earlier in the gameweek but have now kicked off. Use "
        "this context silently to inform your analysis - do not mention "
        "it explicitly. Do not say 'earlier today', 'this week', or "
        "reference games that have already kicked off. Just analyse the "
        "remaining fixtures in front of you as a pundit would - with full "
        "context but without narrating your own history. If form or "
        "injury news from earlier fixtures is relevant to a remaining "
        "fixture, reference it naturally without saying where you got it. "
        "confidence is pre-computed and provided in the data - do not set "
        "it yourself, it will be overwritten anyway. "
        "For double_chance fixtures the pundit_take must describe backing "
        "the away team or the draw - use the pre-computed "
        "double_chance_direction field which says 'Back Away Win or Draw "
        "(X2)'. The home team has a low win probability which is why we "
        "are not backing them. "
        "gameweek_summary must ONLY reference fixtures currently provided "
        "in the data. Never mention any fixture not in the current "
        "match_context - you have no knowledge of other games. "
        f"{rest_of_card_instruction}"
    )
    return "\n\n".join(["\n\n".join(blocks), perf_block, earlier_block, instruction])


# --------------------------------------------------------------------------- #
# STEP 3 - call GPT and parse
# --------------------------------------------------------------------------- #
_CLIENT = None


def _openai_client():
    global _CLIENT
    if _CLIENT is None:
        from openai import OpenAI

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("[strategy] OPENAI_API_KEY not set — using fallback")
            return None
        _CLIENT = OpenAI(api_key=api_key)
    return _CLIENT


def call_gpt(user_prompt: str, extra: str | None = None) -> str | None:
    client = _openai_client()
    if client is None:
        return None
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    if extra:
        messages.append({"role": "user", "content": extra})
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=MAX_TOKENS,
        temperature=0.7,
    )
    return resp.choices[0].message.content or ""


def call_gpt_fix(broken: str) -> str:
    """Ask the model to repair a malformed JSON blob - minimal prompt, temp 0."""
    resp = _openai_client().chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a JSON repair tool. Output only raw JSON, no prose, no code fences."},
            {"role": "user", "content": f"The following JSON is malformed, return only the corrected valid JSON: {broken}"},
        ],
        max_tokens=MAX_TOKENS,
        temperature=0,
    )
    return resp.choices[0].message.content or ""


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t.strip())
    return t.strip()


def _slice_braces(t: str) -> str:
    """Return the substring from the first '{' to the last '}'."""
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1 and end > start:
        return t[start:end + 1]
    return t


def _repair_common(s: str) -> str:
    """Best-effort cleanup of the mistakes gpt-4o-mini makes most often."""
    # smart quotes -> straight quotes
    s = (s.replace("“", '"').replace("”", '"')
           .replace("‘", "'").replace("’", "'"))
    # trailing commas before a closing brace/bracket
    s = re.sub(r",(\s*[}\]])", r"\1", s)
    return s


def _try_loads(s: str):
    """Run one candidate string through every parser we have. Returns dict|None."""
    # 1. strict JSON
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    # 1b. lenient JSON - tolerates raw newlines / tabs inside string values
    try:
        obj = json.loads(s, strict=False)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    # 2. json5 (unquoted keys, single quotes, comments, trailing commas)
    try:
        import json5  # type: ignore

        obj = json5.loads(s)
        if isinstance(obj, dict):
            return obj
    except ImportError:
        pass
    except Exception:
        pass
    # 2b. ast.literal_eval - map JSON literals to Python first
    try:
        import ast

        py = re.sub(r"\bnull\b", "None", s)
        py = re.sub(r"\btrue\b", "True", py)
        py = re.sub(r"\bfalse\b", "False", py)
        obj = ast.literal_eval(py)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return None


def extract_json(text: str, *, allow_llm_repair: bool = True) -> dict:
    """Parse a GPT response into a dict, escalating through fallbacks:

    1. json.loads (strict, then strict=False)
    2. json5 / ast.literal_eval on the cleaned string
    3. regex-extract the outermost { ... } object and retry
    4. last resort: ask GPT to repair the malformed JSON
    """
    stripped = _strip_fences(text)

    candidates = [
        stripped,
        _slice_braces(stripped),
        _repair_common(_slice_braces(stripped)),
    ]
    # 3. regex: greediest outermost braces span
    m = re.search(r"\{.*\}", stripped, re.DOTALL)
    if m:
        candidates.append(_repair_common(m.group(0)))

    for cand in candidates:
        obj = _try_loads(cand)
        if obj is not None:
            return obj

    # 4. hand the broken text back to the model
    if allow_llm_repair:
        fixed = _strip_fences(call_gpt_fix(text))
        for cand in (fixed, _slice_braces(fixed), _repair_common(_slice_braces(fixed))):
            obj = _try_loads(cand)
            if obj is not None:
                return obj

    raise ValueError("Could not parse GPT response as JSON after all fallbacks")


# --------------------------------------------------------------------------- #
# STEP 4 - save
# --------------------------------------------------------------------------- #
def _fx_md(fx: dict) -> str:
    try:
        prob = float(fx.get("prob_homewin", 0) or 0)
    except (TypeError, ValueError):
        prob = 0.0
    try:
        gap = float(fx.get("value_gap", 0) or 0)
    except (TypeError, ValueError):
        gap = 0.0
    return (
        f"### {fx.get('home_team')} vs {fx.get('away_team')} - "
        f"{fx.get('signal')} ({fx.get('confidence')})\n"
        f"{fx.get('edge_label')} | Prob: {prob:.0%} | Odds: {fx.get('odds')} | "
        f"Value: {gap:+.1%}\n"
        f"> {fx.get('pundit_take', '')}\n"
        f"**Action:** {fx.get('pundit_action', '')} | "
        f"**Bet:** {fx.get('bet_type')} | **Stake:** {fx.get('stake_advice')}\n"
    )


def build_markdown(data: dict) -> str:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    parts = [
        f"# EPL AI Pundit Strategy - {date}",
        "*GPT-4o-mini | Not financial advice*",
        "",
        "## Weekend Overview",
        data.get("gameweek_summary", ""),
        "",
        "## Top Picks",
    ]
    parts += [_fx_md(fx) for fx in data.get("top_picks", [])]
    if data.get("rest_of_card_paragraph"):
        parts += ["", "## Pundit's View on the Rest of the Card",
                  data["rest_of_card_paragraph"]]
    parts += ["", "## Value Bets (EDGE)"]
    parts += [_fx_md(fx) for fx in data.get("value_bets", [])]
    parts += ["", "## Avoid This Week"]
    for fx in data.get("avoid_list", []):
        reason = fx.get("pundit_take") or fx.get("reason") or ""
        parts.append(f"- **{fx.get('home_team')} vs {fx.get('away_team')}** - {reason}")
    parts += ["", "## Model Form", data.get("model_form", ""), ""]
    return "\n".join(parts)


def _norm(s: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def enrich_from_context(data: dict, context: dict) -> None:
    """Data cleaning (not AI maths): copy the pre-computed betting_category and
    is_strong_fade fields from match_context.json onto every fixture object in
    the GPT output, matched on team names, so downstream consumers never rely on
    a value the model may have altered.
    """
    ctx = {
        (_norm(fx.get("home_team")), _norm(fx.get("away_team"))): fx
        for fx in context.get("fixtures", [])
    }
    for key in ("top_picks", "strong_fades", "double_chances", "avoid_list",
                "fixtures_full", "value_bets"):
        for fx in data.get(key, []) or []:
            if not isinstance(fx, dict):
                continue
            src = ctx.get((_norm(fx.get("home_team")), _norm(fx.get("away_team"))))
            if src is None:
                continue
            fx["betting_category"] = src.get("betting_category")
            fx["is_strong_fade"] = bool(src.get("is_strong_fade"))


def build_fallback_strategy(context: dict) -> dict:
    """No-AI strategy built purely from the pre-computed match_context numbers.
    Used when the GPT call fails or its JSON cannot be parsed."""
    fixtures = context.get("fixtures", [])
    perf = context.get("model_performance", {})

    top_picks = []
    strong_fades = []
    double_chances = []
    avoid_list = []

    for fx in fixtures:
        cat = fx.get("betting_category", "avoid")
        base = {
            "home_team": fx["home_team"],
            "away_team": fx["away_team"],
            "kickoff": fx["kickoff"],
            "signal": fx["signal"],
            "confidence": "Medium",
            "edge_label": fx["edge_label"],
            "prob_homewin": fx["prob_homewin"],
            "odds": fx["odds"],
            "value_gap": fx["value_gap"],
            "pundit_take": "No AI analysis available for this fixture.",
            "bet_type": "Back Home" if cat == "back_home" else "Back Away Win" if cat == "strong_fade" else "Back Double Chance (X2)" if cat == "double_chance" else "Skip",
            "stake_advice": "Small",
            "pundit_action": "Back Home" if cat == "back_home" else "Strong Fade \u2014 Back Away Win" if cat == "strong_fade" else "Back Double Chance (X2)" if cat == "double_chance" else "Skip \u2014 too close to call",
            "betting_category": cat,
            "rag_informed": False,
        }
        if cat == "back_home":
            top_picks.append(base)
        elif cat == "strong_fade":
            strong_fades.append(base)
        elif cat == "double_chance":
            double_chances.append(base)
        else:
            avoid_list.append(base)

    acc = perf.get("overall_accuracy_pct", 0)
    streak = perf.get("streak_label", "")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_form": f"Model accuracy: {acc}% over last 30. Streak: {streak}.",
        "gameweek_summary": f"AI analysis unavailable. Showing model predictions only. Model is {streak} at {acc}% accuracy.",
        "rest_of_card_paragraph": "",
        "top_picks": top_picks,
        "fixtures_full": top_picks + strong_fades + double_chances + avoid_list,
        "strong_fades": strong_fades,
        "double_chances": double_chances,
        "avoid_list": avoid_list,
        "value_bets": [],
    }


def scrub_percentages(text: str) -> str:
    """Safety-net: strip any percentage/odds figures GPT wrote into free
    text despite the system prompt's CRITICAL RULE against it."""
    # Remove patterns like 93%, 28.1%, 7.8%
    text = re.sub(r'\d+\.?\d*%', '', text)
    # Remove patterns like 1.24 odds, odds of 2.06
    text = re.sub(r'\d+\.\d+ odds', '', text)
    text = re.sub(r'odds of \d+\.\d+', '', text)
    # Clean up double spaces
    text = re.sub(r'  +', ' ', text).strip()
    return text


def scrub_miscategorized_avoid_sentences(text: str, context: dict) -> str:
    """Safety net: GPT doesn't reliably respect betting_category in free
    text - e.g. calling a double_chance fixture "too close to call - skip",
    calling a back_home fixture "double chance", or calling a
    strong_fade/double_chance fixture "back the home". Drop any sentence
    that names a fixture and describes it with language that contradicts
    its pre-computed betting_category."""
    if not text:
        return text

    # Keyed on BOTH home and away team names, so a sentence naming either
    # side of a fixture is still matched to its betting_category.
    fixture_categories: dict[str, str] = {}
    for fx in context["fixtures"]:
        fixture_categories[fx["home_team"]] = fx["betting_category"]
        fixture_categories[fx["away_team"]] = fx["betting_category"]

    avoid_phrases = ["avoid", "skip", "too close to call",
                     "stay away", "give this one a miss",
                     "steer clear"]
    double_chance_phrases = ["double chance", "back the draw", "x2"]
    # Only the specific phrase "back the home" - broader phrases like
    # "at home" false-positive on common pundit language such as "strong
    # at home" or "good at home".
    back_home_phrases = ["back the home"]

    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    kept = []
    for sentence in sentences:
        low = sentence.lower()
        drop = False

        if any(phrase in low for phrase in avoid_phrases):
            if any(team in sentence and cat != "avoid"
                   for team, cat in fixture_categories.items()):
                drop = True

        if not drop and any(phrase in low for phrase in double_chance_phrases):
            if any(team in sentence and cat == "back_home"
                   for team, cat in fixture_categories.items()):
                drop = True

        if not drop and any(phrase in low for phrase in back_home_phrases):
            if any(team in sentence and cat in ("strong_fade", "double_chance")
                   for team, cat in fixture_categories.items()):
                drop = True

        if not drop:
            kept.append(sentence)

    return " ".join(kept).strip()


def enforce_category_bets(data: dict) -> None:
    """Deterministic guard: bet_type / stake_advice / pundit_action must match
    betting_category regardless of what GPT returned."""
    for key in ("top_picks", "strong_fades", "double_chances", "avoid_list",
                "fixtures_full", "value_bets"):
        for fx in data.get(key, []) or []:
            if not isinstance(fx, dict):
                continue
            cat = fx.get("betting_category")
            if cat == "strong_fade":
                fx["bet_type"] = "Back Away Win"
                fx["stake_advice"] = "Small"
                fx["pundit_action"] = "Strong Fade \u2014 Back Away Win"
            elif cat == "double_chance":
                fx["bet_type"] = "Back Double Chance (X2)"
                fx["stake_advice"] = "Small"  # never Skip for double_chance
                fx["pundit_action"] = "Back Double Chance (X2)"
            elif cat == "back_home":
                fx["bet_type"] = "Back Home"
            elif cat == "avoid":
                fx["bet_type"] = "Skip"
                fx["stake_advice"] = "Skip"


def _extract_injury_detail(headline: str, team: str, team_names: set[str] | None = None) -> str | None:
    """Best-effort 'Player (body part)' (or just 'Player') from an injury headline."""
    team_names = team_names or set()
    body_parts = (
        "knee", "hamstring", "ankle", "groin", "calf", "thigh", "shoulder",
        "hip", "achilles", "foot", "back", "toe", "wrist", "elbow", "quad",
        "abductor", "adductor",
    )
    stop = {
        "champions league", "premier league", "europa league", "carabao cup",
        "fa cup", "nations league", "world cup", "super cup", "efl cup",
        "man city", "man united", "man utd", "nottingham forest",
    }
    stop |= {t.lower() for t in team_names}
    stop_words = {w for phrase in stop for w in phrase.split()}
    low = headline.lower()
    tlow = team.lower()
    body = next((b for b in body_parts if b in low), None)
    name = None
    for m in re.finditer(r"\b([A-Z][a-z]+(?:[-'\u2019 ][A-Z][a-z]+)+)\b", headline):
        cand = m.group(1)
        cl = cand.lower()
        if cl in stop:
            continue
        if cl in tlow or any(w in tlow.split() for w in cl.split()):
            continue
        if all(w in stop_words for w in cl.split()):
            continue
        # skip a speaker/manager quoted in the headline ("Alonso provides ...")
        after = headline[m.end():m.end() + 30].lower()
        if re.match(r"\s+(provides?|says?|reveals?|confirms?|gives?|"
                    r"explains?|admits?|addresses|hopes?|expects?|laments?)\b", after):
            continue
        name = cand
        break
    if name and body:
        return f"{name} ({body})"
    if name:
        return name
    if body:
        return f"({body})"
    return None


def build_telegram_from_strategy(data: dict) -> str:
    """The one and only Telegram message - built from the strategy data, never GPT.

    <b>EPL AI Pundit Strategy</b>
    [first sentence of gameweek_summary]

    <b>Top Picks:</b>
    <b>Home vs Away</b> \u2014 action @ odds
    ... (Strong Fades / Double Chance / Injury News sections) ...
    Full analysis: shab00.github.io/football
    """
    lines = ["<b>EPL AI Pundit Strategy</b>"]

    summary = (data.get("gameweek_summary") or "").strip()
    if summary:
        first = re.split(r"(?<=[.!?])\s+", summary)[0].strip()
        if first and first[-1] not in ".!?":
            first += "."
        lines.append(first)
    lines.append("")

    top = data.get("top_picks", []) or []
    if top:
        lines.append("<b>Top Picks:</b>")
        for fx in top:
            lines.append(
                f"<b>{fx['home_team']} vs {fx['away_team']}</b>"
                f" \u2014 {fx.get('pundit_action', 'Back Home')}"
                f" @ {fx.get('odds', '')}"
            )
        lines.append("")

    fades = data.get("strong_fades", []) or []
    if fades:
        lines.append("<b>Strong Fades:</b>")
        for fx in fades:
            lines.append(
                f"<b>{fx['home_team']} vs {fx['away_team']}</b>"
                f" \u2014 Strong Fade \u2014 Back Away Win"
            )
        lines.append("")

    doubles = data.get("double_chances", []) or []
    if doubles:
        lines.append("<b>Double Chance:</b>")
        for fx in doubles:
            lines.append(
                f"<b>{fx['home_team']} vs {fx['away_team']}</b>"
                f" \u2014 Back Double Chance (X2)"
            )
        lines.append("")

    lines.append("<b>Injury News:</b>")
    # compute_context.py's top_headlines() now pre-classifies every
    # home_news/away_news entry into "Name - status" with status one of:
    # out, doubtful, ruled out, misses, unavailable, injury concern - cover
    # all six so none silently vanish from this section.
    injury_words = ("injury", "injured", "knee", "hamstring", "ruled out",
                    "doubt", "unavailable", "setback", "sidelined",
                    "out", "misses")
    injuries: list[str] = []
    try:
        import json as _json
        import pathlib as _pathlib

        ctx = _json.loads(_pathlib.Path("artifacts/match_context.json").read_text())
        for fix in ctx.get("fixtures", []):
            for is_home, feed in ((True, fix.get("home_news", [])),
                                  (False, fix.get("away_news", []))):
                hit = None
                for news in feed:
                    headline = news if isinstance(news, str) else news.get("headline", "")
                    low = headline.lower()
                    # Belt-and-braces: skip fit-player headlines even if
                    # they also match an injury word (e.g. "Pickford
                    # injury news vs Ipswich - is fit and available"
                    # contains "injury" but is not an injury concern).
                    if any(p in low for p in compute_context.FIT_PLAYER_PHRASES):
                        continue
                    if any(w in low for w in injury_words):
                        hit = headline
                        break
                if hit:
                    team = fix["home_team"] if is_home else fix["away_team"]
                    # hit is already "Name - status" from compute_context.py's
                    # top_headlines() - use it directly rather than
                    # re-extracting (which would discard the status).
                    injuries.append(f"{team} \u2014 {hit}")
                    break  # one line per fixture
    except Exception:
        pass
    lines += injuries[:3] if injuries else ["None reported."]

    lines.append("")
    lines.append("Full analysis: shab00.github.io/football")
    return "\n".join(lines)


def _archive_entries() -> list[tuple[datetime, str]]:
    """(archived_at, path) for every archive file whose filename matches
    strategy_YYYYMMDDTHHMMSSZ.json. Files that don't match are ignored."""
    entries = []
    for path in sorted(glob.glob(str(ARCHIVE_DIR / "strategy_*.json"))):
        ts_str = Path(path).stem.removeprefix("strategy_")
        try:
            ts = datetime.strptime(ts_str, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        entries.append((ts, path))
    return entries


def _has_friday_fixture(gw_start: datetime, files: list[tuple[datetime, str]]) -> bool:
    """True if any archive in this gameweek's group has a fixture kicking
    off on the gameweek's Friday."""
    friday_date = gw_start.date()
    for _, path in files:
        try:
            arch = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            continue
        for fx in arch.get("fixtures_full", []) or []:
            kickoff_dt = _parse_kickoff(fx.get("kickoff"))
            if kickoff_dt and kickoff_dt.date() == friday_date:
                return True
    return False


def _closest_pre_kickoff_file(gw_start: datetime, files: list[tuple[datetime, str]]) -> str:
    """The single file from a completed gameweek worth keeping: the one
    closest to the pre-kickoff moment (Friday 18:00 UTC if there's a
    Friday fixture, else Saturday 12:00 UTC) - not the most recent."""
    if _has_friday_fixture(gw_start, files):
        target = gw_start.replace(hour=18, minute=0, second=0, microsecond=0)
    else:
        saturday = gw_start + timedelta(days=1)
        target = saturday.replace(hour=12, minute=0, second=0, microsecond=0)
    return min(files, key=lambda t: abs((t[0] - target).total_seconds()))[1]


def _archive_meta(path: str) -> tuple[bool, int]:
    """(is_scored, fixture_count) for an archive file - best-effort, both
    default to False/0 if the file is missing or unreadable so a broken
    file is always treated as the lowest priority (safe to prune)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return False, 0
    return data.get("scored") is True, len(data.get("fixtures_full") or [])


def clean_strategy_archive(
    dry_run: bool = False, keep_extra: set[str] | None = None
) -> tuple[list[str], list[str]]:
    """Thin artifacts/strategy_archive/ down to one pre-kickoff snapshot per
    completed gameweek (the RAG's historical record), while keeping a short
    rolling window of recent snapshots for the current gameweek. Never
    touches anything from more than 4 weeks ago - that's valuable RAG
    history regardless of how many snapshots pile up.

    Within a gameweek group, files are prioritised scored > real unscored
    (fixtures_full non-empty) > empty - a scored file is NEVER deleted no
    matter how many exist, and an empty/garbage file is always the first
    to go, never a real prediction file, while any real or scored data
    exists to keep instead.

    keep_extra: manual override paths to always keep on top of the normal
    selection - e.g. one-off early history predating the usual gameweek
    grouping. Not used by the automatic main() call.

    Returns (kept_paths, deleted_paths). With dry_run=True nothing is
    actually deleted - it just reports the plan.
    """
    now = datetime.now(timezone.utc)
    current_window = compute_context.get_gameweek_window(now)
    four_weeks_ago = now - timedelta(weeks=4)

    entries = _archive_entries()

    groups: dict[tuple[datetime, datetime], list[tuple[datetime, str]]] = {}
    for ts, path in entries:
        gw = compute_context.get_gameweek_window(ts)
        groups.setdefault(gw, []).append((ts, path))

    keep: set[str] = set(keep_extra or ())
    for (gw_start, gw_end), files in groups.items():
        files.sort(key=lambda t: t[0])
        oldest_ts = files[0][0]

        if oldest_ts < four_weeks_ago:
            # Older than 4 weeks - never delete, keep everything as-is.
            keep.update(p for _, p in files)
            continue

        meta = {p: _archive_meta(p) for _, p in files}
        scored = [(ts, p) for ts, p in files if meta[p][0]]
        unscored = [(ts, p) for ts, p in files if not meta[p][0]]
        real_unscored = [(ts, p) for ts, p in unscored if meta[p][1] > 0]
        empty_unscored = [(ts, p) for ts, p in unscored if meta[p][1] == 0]

        # Never delete a scored file, regardless of count caps below.
        keep.update(p for _, p in scored)

        if (gw_start, gw_end) == current_window:
            # Current gameweek - keep up to 3 total for fresh RAG context,
            # counting the scored files already kept toward that cap, and
            # filling any remaining slots from the most recent REAL files
            # first, only reaching for empty ones if there aren't enough.
            slots = max(0, 3 - len(scored))
            if slots:
                ordered = (
                    sorted(real_unscored, key=lambda t: t[0])
                    + sorted(empty_unscored, key=lambda t: t[0])
                )
                keep.update(p for _, p in ordered[-slots:])
        else:
            # Completed gameweek - a scored file already satisfies "one per
            # gameweek"; only fall back to an unscored file if there isn't
            # one yet, preferring a real file over an empty one.
            if not scored:
                pool = real_unscored if real_unscored else empty_unscored
                if pool:
                    keep.add(_closest_pre_kickoff_file(gw_start, pool))

    deleted = [path for _, path in entries if path not in keep]
    kept = [path for _, path in entries if path in keep]

    if not dry_run:
        for path in deleted:
            Path(path).unlink(missing_ok=True)

    print(f"[strategy] archive: {len(kept)} files kept, {len(deleted)} deleted")
    return kept, deleted


# --------------------------------------------------------------------------- #
# No-fixtures mode: when the gameweek window holds no upcoming fixtures there
# is nothing to predict, so we skip GPT strategy generation entirely and
# instead publish a "next matchday" flag plus a pundit review of the gameweek
# just gone.
# --------------------------------------------------------------------------- #

LOOKBACK_SYSTEM_PROMPT = (
    "You are an opinionated football pundit reviewing last weekend's Premier "
    "League results. Write a natural, engaging 3-4 sentence review of how the "
    "model performed. Reference specific fixtures, scores and whether the "
    "model called them correctly. Use natural pundit language - 'didn't see "
    "that coming', 'model nailed this one', 'had to eat humble pie on that "
    "one'. Do not mention probabilities or model internals. Write as if "
    "speaking to fans. "
    "The model only predicts Home win or Not Home win - never scores. Do "
    "not invent or reference predicted scorelines. "
    "Only use stake labels (banker, value bet, small) from the data "
    "provided. Do not invent them. "
    "Do not say a result was 'supposed to be a banker' unless stake_advice "
    "in the data explicitly says Banker. "
    "You may reference the actual final score if it is provided in the "
    "data. Do not invent scores. "
    "The result description tells you exactly who won. Do not use your own "
    "knowledge of these matches - only reference what is written here."
)

# Below this many hours old, the most recent result in results_merged.csv is
# treated as still "settling" - football-data.co.uk lags real kickoffs by up
# to a day, and Monday night games mean a gameweek's last result may not be
# confirmed until Tuesday.
LOOKBACK_READY_HOURS = 18


def compute_next_matchday() -> str | None:
    """Earliest future kickoff date (YYYY-MM-DD) in the predictions snapshot
    that the model actually predicts (is_predicted_fixture == 1). Returns
    None if the snapshot is missing, unreadable or holds no future
    predicted fixture."""
    if not PREDICTIONS_CSV.exists():
        return None
    try:
        import pandas as pd

        df = pd.read_csv(PREDICTIONS_CSV)
        if "is_predicted_fixture" not in df.columns:
            return None
        kd = pd.to_datetime(df["kickoff_time_utc"], errors="coerce", utc=True)
        predicted = pd.to_numeric(df["is_predicted_fixture"], errors="coerce") == 1
        future = kd[predicted & kd.notna() & (kd > datetime.now(timezone.utc))]
        if future.empty:
            return None
        return future.min().strftime("%Y-%m-%d")
    except Exception as exc:  # noqa: BLE001
        print(f"[strategy] warn: could not compute next matchday: {exc}")
        return None


def latest_scored_archive() -> dict | None:
    """The most recent archived strategy that has been scored against real
    results - the pundit's raw material for the lookback review."""
    scored = load_scored_archive()
    if not scored:
        return None
    return sorted(scored, key=lambda a: a.get("_path", ""))[-1]


def check_lookback_ready() -> tuple[bool, datetime | None]:
    """Whether results_merged.csv's most recent kickoff is old enough to
    trust for the lookback review, or whether results may still be coming
    in (see LOOKBACK_READY_HOURS). Returns (ready, most_recent_kickoff) -
    ready defaults to True when there is no data to wait on at all (missing
    file, empty file, or no parseable kickoff)."""
    if not RESULTS_CSV.exists():
        return True, None
    try:
        import pandas as pd

        df = pd.read_csv(RESULTS_CSV)
        if df.empty:
            return True, None
        col = "kickoff_dt" if "kickoff_dt" in df.columns else "kickoff_time_utc"
        kd = pd.to_datetime(df[col], errors="coerce", utc=True).dropna()
        if kd.empty:
            return True, None
        most_recent = kd.max().to_pydatetime()
        age_hours = (datetime.now(timezone.utc) - most_recent).total_seconds() / 3600
        return age_hours >= LOOKBACK_READY_HOURS, most_recent
    except Exception as exc:  # noqa: BLE001
        print(f"[strategy] warn: could not check lookback readiness: {exc}")
        return True, None


def build_lookback_results_lines(archive: dict | None) -> list[str]:
    """Exact-format 'model predicted vs result' lines built dynamically
    from the scored archive's fixtures_full - correct, FTR, signal,
    stake_advice, edge_label. Never hardcoded: any archive, any fixtures.
    A fixture without a scored FTR is skipped rather than guessed at.

    The result is spelled out as a plain-English sentence naming the actual
    team that won ("Brighton won at home"), rather than a bare FTR code -
    GPT has repeatedly misread a raw "FTR: H" as the first-named team
    winning regardless of home/away, or substituted its own training-data
    memory of the fixture instead of the literal result given here.
    """
    if not archive:
        return []

    lines: list[str] = []
    for fx in archive.get("fixtures_full", []) or []:
        home = fx.get("home_team")
        away = fx.get("away_team")
        ftr = fx.get("FTR")
        signal = fx.get("signal", "")
        correct = fx.get("correct")

        if ftr == "H":
            result_str = f"{home} won at home"
        elif ftr == "A":
            result_str = f"{away} won away"
        elif ftr == "D":
            result_str = "the match ended in a draw"
        else:
            continue  # not actually scored yet - skip rather than guess

        edge_label = fx.get("edge_label")
        stake_advice = (fx.get("stake_advice") or "").strip()

        # Only "back_home" bets ever carry a Banker/Value Bet stake in this
        # pipeline (fades/double-chances/avoids are forced to Small/Skip by
        # enforce_category_bets), so the qualifier only ever applies to a
        # "Home" signal - matching the app's own "Back Home (Banker)" /
        # "Back Home (Value)" convention used elsewhere.
        annotation = ""
        if signal == "Home" and edge_label and edge_label != "N/A":
            if stake_advice.lower() == "banker":
                annotation = f" ({edge_label} banker)"
            else:
                annotation = f" ({edge_label})"

        correct_str = "CORRECT" if correct else "WRONG"
        lines.append(
            f"{home} vs {away} — model predicted: {signal}{annotation} — "
            f"{result_str} — model was {correct_str}"
        )
    return lines


def recent_results(n: int = LOOKBACK_RESULTS_N) -> list[dict]:
    """The n most recent scored rows from results_merged.csv. The file is
    written newest-first (merge_results.py sorts desc on generated_at), so
    the most recent n are the head rows."""
    if not RESULTS_CSV.exists():
        return []
    try:
        import pandas as pd

        df = pd.read_csv(RESULTS_CSV)
        df = df[df["FTR"].notna() & (df["FTR"].astype(str).str.strip() != "")]
        if "generated_at" in df.columns:
            df = df.sort_values("generated_at", ascending=False)
        wanted = ["home_team", "away_team", "FTHG", "FTAG", "FTR",
                  "prediction", "correct"]
        cols = [c for c in wanted if c in df.columns]
        return df[cols].head(n).to_dict("records")
    except Exception as exc:  # noqa: BLE001
        print(f"[strategy] warn: could not read recent results: {exc}")
        return []


def build_lookback_summary(archive: dict | None, results: list[dict]) -> str:
    """Ask GPT-4o-mini for a short pundit review of the gameweek just gone.
    Returns "" if there is nothing to review or the call fails - the page
    simply omits the review rather than showing an error.

    The mandatory "model predicted ... result ... CORRECT/WRONG" block is
    built dynamically from the scored archive (never hardcoded) and is the
    ONLY data GPT is told to review. A short supplementary block of real
    final scores (matched from results_merged.csv) is appended separately
    so GPT can optionally cite a real scoreline without ever being allowed
    to invent one for the mandatory block.
    """
    result_lines = build_lookback_results_lines(archive)
    if not result_lines:
        return ""

    prompt_parts = [
        "Here are the exact results to review. Reference ONLY these - do "
        "not invent scores, predictions or stake labels:",
        "",
        "\n".join(result_lines),
    ]

    scores_by_fixture = {
        (r.get("home_team"), r.get("away_team")): (r.get("FTHG"), r.get("FTAG"))
        for r in results
    }
    score_lines = []
    for fx in (archive.get("fixtures_full") or []) if archive else []:
        key = (fx.get("home_team"), fx.get("away_team"))
        if key not in scores_by_fixture:
            continue
        fthg, ftag = scores_by_fixture[key]
        try:
            score_lines.append(
                f"- {fx['home_team']} {int(float(fthg))}-{int(float(ftag))} "
                f"{fx['away_team']}"
            )
        except (TypeError, ValueError):
            continue
    if score_lines:
        prompt_parts += [
            "",
            "Actual final scores (only reference these if useful - never "
            "invent any others):",
            "\n".join(score_lines),
        ]

    user_prompt = "\n".join(prompt_parts)

    try:
        client = _openai_client()
        if client is None:
            print("[strategy] no API key - skipping lookback review")
            return ""
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": LOOKBACK_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=400,
            temperature=0.7,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        print(f"[strategy] warn: lookback review unavailable ({exc})")
        return ""


def write_no_fixtures_strategy() -> dict:
    """Publish the no-fixtures payload: a mode flag, the next matchday and,
    once results have had time to settle, a pundit lookback review. No
    fixture strategy is generated and the main GPT strategy call is never
    made."""
    next_matchday = compute_next_matchday()
    lookback_ready, most_recent_kickoff = check_lookback_ready()

    lookback = ""
    if lookback_ready:
        archive = latest_scored_archive()
        results = recent_results()
        lookback = build_lookback_summary(archive, results)
    else:
        print(
            f"[strategy] most recent result kicked off {most_recent_kickoff} "
            f"(<{LOOKBACK_READY_HOURS}h ago) - results may still be coming "
            "in, skipping lookback GPT call"
        )

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "no_fixtures",
        "next_matchday": next_matchday,
        "lookback_ready": lookback_ready,
        "lookback_summary": lookback,
        "gameweek_summary": "",
        "rest_of_card_paragraph": "",
        "top_picks": [],
        "strong_fades": [],
        "double_chances": [],
        "avoid_list": [],
        "fixtures_full": [],
        "value_bets": [],
    }

    LATEST_JSON.parent.mkdir(parents=True, exist_ok=True)
    LATEST_JSON.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print("[strategy] no fixtures in the current gameweek - skipped GPT strategy")
    print(f"[strategy] next matchday: {next_matchday or 'unknown'}")
    print(f"[strategy] lookback_ready: {lookback_ready}")
    print(f"[strategy] lookback review: {'yes' if lookback else 'none'}")
    print(f"[strategy] wrote {LATEST_JSON}")

    # Archive cleanup must run here too, not just in the normal (has-fixtures)
    # path - otherwise empty/garbage snapshots accumulate between gameweeks
    # whenever a run lands in no-fixtures mode.
    clean_strategy_archive(
        keep_extra={str(ARCHIVE_DIR / name) for name in PROTECTED_ARCHIVE_FILES}
    )

    return data


# --------------------------------------------------------------------------- #
# One-time repair: GW5 (2026-09-19/20) never ended up with a real scored
# archive - clean_strategy_archive()'s old bug thinned that gameweek down to
# nothing but empty/garbage snapshots (see the fix above). This rebuilds it
# directly from the real results_merged.csv rows so the RAG and pundit
# lookback review have genuine GW5 history to draw from.
# --------------------------------------------------------------------------- #

GW5_ARCHIVE_PATH = ARCHIVE_DIR / "strategy_20260919T140000Z.json"

# The exact GW5 fixtures to reconstruct - also used as a sanity check that
# results_merged.csv actually has the rows we expect.
GW5_FIXTURE_KEYS = {
    ("Fulham", "Man United"),
    ("Leeds", "Crystal Palace"),
    ("Man City", "Sunderland"),
    ("Bournemouth", "Liverpool"),
    ("Nott'm Forest", "Coventry City"),
    ("Everton", "Ipswich Town"),
    ("Newcastle", "Hull City"),
    ("Brighton", "Arsenal"),
    ("Tottenham", "Aston Villa"),
}


def reconstruct_gw5_archive() -> None:
    """Rebuild artifacts/strategy_archive/strategy_20260919T140000Z.json from
    the real results_merged.csv rows for GW5. A no-op once the file exists -
    this only ever needs to run once.

    betting_category and edge_label are derived from each fixture's real
    prob_homewin/odds_B365H using the exact same logic compute_context.py
    uses live, rather than hardcoding labels - so the reconstruction stays
    consistent with how the rest of the pipeline actually computes them.
    """
    if GW5_ARCHIVE_PATH.exists():
        return

    if not RESULTS_CSV.exists():
        print(f"[strategy] cannot reconstruct GW5 archive - {RESULTS_CSV} missing")
        return

    try:
        import pandas as pd

        df = pd.read_csv(RESULTS_CSV)
        gw5 = df[df["kickoff_time_utc"].astype(str).str.startswith(("2026-09-19", "2026-09-20"))]
    except Exception as exc:  # noqa: BLE001
        print(f"[strategy] warn: could not read {RESULTS_CSV} for GW5 reconstruction: {exc}")
        return

    fixtures_full = []
    for _, r in gw5.iterrows():
        key = (str(r.get("home_team")), str(r.get("away_team")))
        if key not in GW5_FIXTURE_KEYS:
            continue  # not one of the known GW5 fixtures - skip defensively

        prob = float(r.get("prob_homewin", 0) or 0)
        try:
            odds = float(r.get("odds_B365H"))
        except (TypeError, ValueError):
            odds = None
        signal = str(r.get("prediction", ""))
        ftr = str(r.get("FTR", ""))
        correct = str(r.get("correct", "")).strip().lower() == "true"

        cat = compute_context.betting_category(prob)
        if signal == "Home" and odds and odds > 0:
            value_gap = prob - (1.0 / odds)
            edge_label = "EDGE" if value_gap > 0 else "FADE"
        else:
            edge_label = "N/A"

        if cat == "back_home":
            stake_advice = "Banker" if edge_label == "EDGE" else "Value Bet"
            pundit_action = f"Back Home ({stake_advice})"
        elif cat == "strong_fade":
            stake_advice = "Small"
            pundit_action = "Strong Fade — Back Away Win"
        elif cat == "double_chance":
            stake_advice = "Small"
            pundit_action = "Back Double Chance (X2)"
        else:  # avoid
            stake_advice = "Skip"
            pundit_action = "Skip — too close to call"

        fixtures_full.append({
            "home_team": r.get("home_team"),
            "away_team": r.get("away_team"),
            "kickoff": str(r.get("kickoff_time_utc")),
            "signal": signal,
            "betting_category": cat,
            "edge_label": edge_label,
            "stake_advice": stake_advice,
            "pundit_action": pundit_action,
            "is_strong_fade": bool(prob < 0.20),
            "correct": correct,
            "FTR": ftr,
        })

    if len(fixtures_full) != len(GW5_FIXTURE_KEYS):
        print(
            f"[strategy] warn: GW5 reconstruction found {len(fixtures_full)}/"
            f"{len(GW5_FIXTURE_KEYS)} expected fixtures in {RESULTS_CSV} - "
            "writing archive with what was found"
        )

    confident = [fx for fx in fixtures_full if fx["signal"] != "Avoid"]
    n_confident = len(confident)
    n_correct = sum(1 for fx in confident if fx["correct"])

    archive = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scored": True,
        "gameweek": "2026-09-19",
        "fixtures_full": fixtures_full,
        "score_summary": {
            "total_fixtures": len(fixtures_full),
            "confident_predictions": n_confident,
            "correct": n_correct,
            "accuracy_pct": round(n_correct / n_confident * 100, 1) if n_confident else 0.0,
        },
    }

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    GW5_ARCHIVE_PATH.write_text(
        json.dumps(archive, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"[strategy] reconstructed GW5 scored archive: {GW5_ARCHIVE_PATH} "
        f"({len(fixtures_full)} fixtures, {n_correct}/{n_confident} correct)"
    )


def main() -> None:
    reconstruct_gw5_archive()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--debug",
        action="store_true",
        help="print the raw GPT response before parsing",
    )
    args = parser.parse_args()

    load_dotenv(override=False)

    if not CONTEXT_JSON.exists():
        raise SystemExit(f"[strategy] missing {CONTEXT_JSON} - run compute_context.py first")
    context = json.loads(CONTEXT_JSON.read_text(encoding="utf-8"))
    fixtures = context.get("fixtures", [])

    # --- NO-FIXTURES GUARD ---------------------------------------------------
    # Nothing to predict this gameweek: publish the next-matchday flag plus a
    # pundit lookback review and exit without ever calling the strategy GPT.
    if not fixtures:
        write_no_fixtures_strategy()
        return

    # --- STEP 1: RAG ---------------------------------------------------------
    archives = load_scored_archive()
    past_fixtures = collect_past_fixtures(archives)
    pool_filter = maybe_build_faiss(past_fixtures, len(archives))

    rag_by_fixture: list[str] = []
    n_rag = 0
    for fx in fixtures:
        ctx, n = build_rag_context(fx, past_fixtures, pool_filter)
        rag_by_fixture.append(ctx)
        n_rag += n

    # --- STEP 2 + 3: prompt + call ----------------------------------------
    user_prompt = build_user_prompt(context, rag_by_fixture)
    parsed_via = "primary"
    try:
        raw = call_gpt(user_prompt)
        if raw is None:
            data = build_fallback_strategy(context)
            parsed_via = "fallback (no AI)"
            print("[strategy] using fallback strategy (no API key)")
        else:
            if args.debug:
                print("=" * 72)
                print("[strategy] RAW GPT RESPONSE:")
                print(raw)
                print("=" * 72)
            try:
                data = extract_json(raw, allow_llm_repair=False)
            except Exception:
                raw = call_gpt(user_prompt, extra="Return only valid JSON")
                if raw is None:
                    raise RuntimeError("OPENAI_API_KEY not set")
                if args.debug:
                    print("[strategy] RAW GPT RESPONSE (retry with 'Return only valid JSON'):")
                    print(raw)
                    print("=" * 72)
                data = extract_json(raw, allow_llm_repair=True)
                parsed_via = "retry + fallback ladder"
    except Exception as exc:  # noqa: BLE001
        print(f"[strategy] GPT unavailable ({exc}); building fallback strategy "
              f"from {CONTEXT_JSON.name} with no AI")
        data = build_fallback_strategy(context)
        parsed_via = "fallback (no AI)"

    if args.debug:
        print(f"[strategy] parsed via {parsed_via}; top-level keys: {sorted(data.keys())}")
        for _arr in ("fixtures_full", "top_picks", "strong_fades",
                     "double_chances", "avoid_list"):
            for _fx in data.get(_arr, []) or []:
                if not isinstance(_fx, dict):
                    continue
                if "leeds" in f"{_fx.get('home_team')} {_fx.get('away_team')}".lower():
                    print(f"[strategy][debug] RAW (pre-Pydantic) {_fx.get('home_team')} vs "
                          f"{_fx.get('away_team')} value_gap = {_fx.get('value_gap')!r} "
                          f"prob_homewin = {_fx.get('prob_homewin')!r}  [{_arr}]")

    # generated_at must exist before Pydantic validation (required field)
    data.setdefault("generated_at", datetime.now(timezone.utc).isoformat())

    # --- Pydantic v2 validation + normalisation (prob_homewin / value_gap /
    # edge_label are normalised + clamped by the field validators) ---------
    try:
        data = WeekendStrategy(**data).model_dump()
        print("[strategy] Pydantic validation OK")
    except Exception as e:  # noqa: BLE001
        print(f"[strategy] Pydantic validation warning: {e}")

    # rest_of_card_paragraph only makes sense with >=2 remaining fixtures -
    # with 0 or 1 remaining, the pundit just analyses that fixture
    # directly. GPT was told not to write the field at all in this case,
    # but force it empty here regardless of what GPT actually returned.
    if len(fixtures) <= 1:
        data["rest_of_card_paragraph"] = ""

    # GPT does not transcribe numeric values reliably (it invents its own
    # prob_homewin/odds instead of copying them) - never trust its numbers.
    # Overwrite every fixture's numeric fields and computed labels from
    # match_context.json, the source of truth. GPT only supplies text
    # fields (pundit_take, confidence, stake_advice).
    ctx_lookup = {
        f"{fx['home_team']}|{fx['away_team']}": fx
        for fx in context["fixtures"]
    }
    for array_name in ["fixtures_full", "top_picks", "strong_fades",
                       "double_chances", "avoid_list"]:
        for fx in data.get(array_name, []):
            key = f"{fx['home_team']}|{fx['away_team']}"
            if key in ctx_lookup:
                ctx = ctx_lookup[key]
                fx["prob_homewin"] = ctx["prob_homewin"]
                fx["odds"] = ctx["odds"]
                fx["value_gap"] = ctx["value_gap"]
                fx["edge_label"] = ctx["edge_label"]
                fx["betting_category"] = ctx["betting_category"]
                fx["signal"] = ctx["signal"]
                fx["confidence"] = ctx["confidence"]
                fx["bet_description"] = ctx["bet_description"]
                fx["double_chance_direction"] = ctx.get(
                    "double_chance_direction", "")

    # Post-process: recompute value_gap in Python from the pre-computed
    # prob_homewin and odds - never trust GPT's arithmetic.
    for array_name in ["fixtures_full", "top_picks", "strong_fades",
                       "double_chances", "avoid_list"]:
        for fx in data.get(array_name, []):
            try:
                prob = float(fx.get("prob_homewin", 0))
                odds = float(fx.get("odds", 0))
                if odds > 0:
                    fx["value_gap"] = round(prob - (1 / odds), 4)
            except (TypeError, ValueError):
                fx["value_gap"] = 0.0

    enrich_from_context(data, context)
    enforce_category_bets(data)

    # Section placement is deterministic, never GPT's call - GPT only
    # contributes pundit_take text. Rebuild top_picks / strong_fades /
    # double_chances / avoid_list from fixtures_full purely on the
    # (now-authoritative) betting_category field.
    top_picks = []
    strong_fades = []
    double_chances = []
    avoid_list = []

    for fx in data.get("fixtures_full", []):
        cat = fx.get("betting_category", "")
        if cat == "back_home":
            top_picks.append(fx)
        elif cat == "strong_fade":
            strong_fades.append(fx)
        elif cat == "double_chance":
            double_chances.append(fx)
        elif cat == "avoid":
            avoid_list.append(fx)

    data["top_picks"] = top_picks
    data["strong_fades"] = strong_fades
    data["double_chances"] = double_chances
    data["avoid_list"] = avoid_list

    # Ensure fixtures_full is complete
    ctx_keys = {
        f"{fx['home_team']}|{fx['away_team']}"
        for fx in context["fixtures"]
    }
    existing_keys = {
        f"{fx['home_team']}|{fx['away_team']}"
        for fx in data.get("fixtures_full", [])
    }
    missing_keys = ctx_keys - existing_keys

    if missing_keys:
        print(f"[strategy] GPT omitted {len(missing_keys)} fixtures — injecting from context")
        for fx in context["fixtures"]:
            key = f"{fx['home_team']}|{fx['away_team']}"
            if key in missing_keys:
                # Build a fallback fixture object from context
                fallback = {
                    "home_team": fx["home_team"],
                    "away_team": fx["away_team"],
                    "kickoff": fx["kickoff"],
                    "signal": fx["signal"],
                    "confidence": fx["confidence"],
                    "edge_label": fx["edge_label"],
                    "prob_homewin": fx["prob_homewin"],
                    "odds": fx["odds"],
                    "value_gap": fx["value_gap"],
                    "betting_category": fx["betting_category"],
                    "bet_description": fx["bet_description"],
                    "double_chance_direction": fx.get("double_chance_direction",""),
                    "pundit_take": "Model signal only — no AI analysis for this fixture.",
                    "bet_type": fx["bet_description"],
                    "stake_advice": "Small",
                    "pundit_action": fx["bet_description"],
                    "rag_informed": False
                }
                data["fixtures_full"].append(fallback)
                print(f"[strategy] injected: {key}")

    # Re-run section enforcement after injection
    top_picks = []
    strong_fades = []
    double_chances = []
    avoid_list = []
    for fx in data.get("fixtures_full", []):
        cat = fx.get("betting_category", "")
        if cat == "back_home":
            top_picks.append(fx)
        elif cat == "strong_fade":
            strong_fades.append(fx)
        elif cat == "double_chance":
            double_chances.append(fx)
        elif cat == "avoid":
            avoid_list.append(fx)

    data["top_picks"] = top_picks
    data["strong_fades"] = strong_fades
    data["double_chances"] = double_chances
    data["avoid_list"] = avoid_list

    # model_form is ALWAYS built from match_context.json - never GPT, never stale.
    perf = context.get("model_performance", {})
    data["model_form"] = (
        f"Model is {perf.get('streak_label', '')} \u2014 "
        f"{perf.get('overall_accuracy_pct', 0)}% accuracy "
        f"over last {perf.get('total_predictions', 0)} confident predictions. "
        f"EDGE profit: {perf.get('edge_profit', 0):+.2f} units."
    )

    # Guarantee the rest-of-card paragraph carries a mention of model form
    # (gpt-4o-mini often paraphrases it away). Qualitative only - no
    # accuracy percentage - per the CRITICAL RULE against numbers in free
    # text. Only applies when the field exists at all (>=2 fixtures).
    if len(fixtures) >= 2:
        _streak = perf.get("streak_label", "")
        _para = (data.get("rest_of_card_paragraph") or "").strip()
        if _streak and _streak.upper() not in _para.upper():
            _sfx = (f" The model is currently {_streak} over its last "
                    f"{perf.get('total_predictions', 0)} confident predictions.")
            data["rest_of_card_paragraph"] = (_para + _sfx).strip()

    # Safety net: strip any percentage/probability/odds figures GPT wrote
    # into free text despite the system prompt's CRITICAL RULE against it.
    data["gameweek_summary"] = scrub_percentages(data.get("gameweek_summary") or "")
    data["rest_of_card_paragraph"] = scrub_percentages(data.get("rest_of_card_paragraph") or "")
    data["rest_of_card_paragraph"] = scrub_miscategorized_avoid_sentences(
        data.get("rest_of_card_paragraph") or "", context
    )
    for array_name in ["fixtures_full", "top_picks", "strong_fades",
                       "double_chances", "avoid_list", "value_bets"]:
        for fx in data.get(array_name, []) or []:
            if isinstance(fx, dict) and fx.get("pundit_take"):
                fx["pundit_take"] = scrub_percentages(fx["pundit_take"])

    # FILTER 1 - drop fixtures that are not in the current gameweek context.
    valid_keys = {
        f"{fx['home_team']}|{fx['away_team']}"
        for fx in context["fixtures"]
    }
    for array_name in ["top_picks", "strong_fades", "double_chances",
                       "avoid_list", "fixtures_full"]:
        data[array_name] = [
            fx for fx in data.get(array_name, []) or []
            if f"{fx.get('home_team')}|{fx.get('away_team')}" in valid_keys
        ]

    # FILTER 2 - drop fixtures with zero prob_homewin or zero odds.
    for array_name in ["top_picks", "strong_fades", "double_chances",
                       "avoid_list", "fixtures_full"]:
        kept = []
        for fx in data.get(array_name, []) or []:
            try:
                if float(fx.get("prob_homewin", 0)) > 0 and float(fx.get("odds", 0)) > 0:
                    kept.append(fx)
            except (TypeError, ValueError):
                continue
        data[array_name] = kept

    # Telegram message is ALWAYS built deterministically from the strategy
    # data - GPT never generates it (avoids two competing messages).
    data["telegram_message"] = build_telegram_from_strategy(data)

    # --- STEP 4: save -----------------------------------------------------
    LATEST_JSON.parent.mkdir(parents=True, exist_ok=True)
    LATEST_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    LATEST_MD.write_text(build_markdown(data), encoding="utf-8")

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_copy = dict(data)
    archive_copy["scored"] = False
    (ARCHIVE_DIR / f"strategy_{ts}.json").write_text(
        json.dumps(archive_copy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    n_top = len(data.get("top_picks", []))
    n_sf = len(data.get("strong_fades", []))
    n_dc = len(data.get("double_chances", []))
    n_fx = len(data.get("fixtures_full", fixtures))
    print(
        f"[strategy] {n_fx} fixtures | {n_top} top picks | {n_sf} strong fades | "
        f"{n_dc} double chances | RAG: {n_rag} matches retrieved"
    )
    print(f"[strategy] wrote {LATEST_JSON}")

    clean_strategy_archive(
        keep_extra={str(ARCHIVE_DIR / name) for name in PROTECTED_ARCHIVE_FILES}
    )


if __name__ == "__main__":
    main()
