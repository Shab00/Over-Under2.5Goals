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
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, field_validator
from typing import Literal


class FixtureStrategy(BaseModel):
    home_team: str
    away_team: str
    kickoff: str
    signal: Literal["Home", "Not Home", "Avoid"]
    confidence: Literal["High", "Medium", "Low"]
    edge_label: Literal["EDGE", "FADE", "N/A"]
    prob_homewin: float
    odds: float
    value_gap: float
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
LATEST_JSON = Path("artifacts/strategy_latest.json")
LATEST_MD = Path("artifacts/strategy_latest.md")
FAISS_INDEX = Path("artifacts/strategy_faiss.index")

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
    "OUTPUT ARRAYS\n"
    "Populate these arrays in your response:\n"
    "- top_picks: all fixtures where betting_category==back_home\n"
    "- strong_fades: all fixtures where betting_category==strong_fade\n"
    "- double_chances: all fixtures where betting_category==double_chance\n"
    "- avoid_list: all fixtures where betting_category==avoid\n"
    "Also populate fixtures_full with every fixture.\n\n"
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
    "GAMEWEEK SUMMARY\n"
    "gameweek_summary must name specific teams and facts. Mention: the "
    "standout value bet by name, the biggest mismatch fixture, and one "
    "specific named injury if any exists in the news data. No generic "
    "statements.\n\n"
    "REST OF THE CARD PARAGRAPH\n"
    "Generate a field called rest_of_card_paragraph. This is a pundit's "
    "summary paragraph covering the strong fades, double chance and avoid "
    "fixtures.\n"
    "Rules:\n"
    "- Write in natural pundit voice - opinionated, direct\n"
    "- Use ONLY the pre-computed prob_homewin percentages provided in the "
    "data - never invent figures\n"
    "- Reference specific betting_category thresholds: strong_fade = below "
    "30% home win probability; double_chance = 30-45% home win probability; "
    "avoid = 45-55% too close to call\n"
    "- Reference specific injury news from home_news and away_news where "
    "relevant - name the player\n"
    "- You MUST cite the model's recent performance using the exact "
    "figures provided: the overall_accuracy_pct number, the "
    "streak_label word (e.g. HOT), and the edge_profit units\n"
    "- Reference h2h or form data where it strengthens the argument\n"
    "- Do NOT use phrases like 'keep an eye on' or generic disclaimers\n"
    "- Structure naturally: start with strong fades, move to double "
    "chances, end with avoids\n"
    "- Keep it under 120 words\n"
    "- Sound like a pundit who has studied the numbers and the news, not a "
    "robot reading a spreadsheet\n"
    "Example tone (do not copy this exactly - use real data from this "
    "week): 'The Manchester derby is as close to a no-bet as it gets for "
    "the home side - United are at just 10% which is a signal to back City "
    "all day. Similarly Sunderland hosting Arsenal at 30% is a strong "
    "fade. For those looking at double chances, Villa at 41% against "
    "Forest is interesting but Goretzka's knee injury weakens their "
    "midfield and the h2h favours a tight game. Leeds vs Newcastle at 42% "
    "is another one to take double chance rather than back the home side. "
    "The model is currently HOT at 63% accuracy over the last 30 - trust "
    "the signals this week.'"
)

FIXTURE_SCHEMA = """{
  "home_team": "...",
  "away_team": "...",
  "kickoff": "...",
  "signal": "Home|Not Home|Avoid",
  "confidence": "High|Medium|Low",
  "edge_label": "EDGE|FADE|N/A",
  "prob_homewin": 0.0,
  "odds": 0.0,
  "value_gap": 0.0,
  "betting_category": "back_home|avoid|double_chance|strong_fade (PRE-COMPUTED, keep exactly)",
  "is_strong_fade": true/false,
  "pundit_take": "2-3 sentence analysis",
  "pundit_action": "determined by betting_category EXACTLY: back_home -> 'Back Home (Banker)' or 'Back Home (Value)'; avoid -> 'Skip \u2014 too close to call'; double_chance -> 'Back Double Chance (X2)'; strong_fade -> 'Strong Fade \u2014 Back Away Win'",
  "bet_type": "Back Home|Lay Home|Skip",
  "stake_advice": "Banker|Value Bet|Small|Skip",
  "rag_informed": true/false
}"""

OUTPUT_SCHEMA = """{
  "generated_at": "ISO datetime",
  "model_form": "one sentence on recent model form",
  "gameweek_summary": "2-3 sentence pundit overview",
  "rest_of_card_paragraph": "single flowing pundit paragraph (<120 words) covering strong fades, double chances then avoids, using ONLY pre-computed prob_homewin percentages and named injury news",
  "top_picks": [...all betting_category==back_home fixture objects...],
  "strong_fades": [...all betting_category==strong_fade fixture objects...],
  "double_chances": [...all betting_category==double_chance fixture objects...],
  "avoid_list": [...all betting_category==avoid fixture objects...],
  "fixtures_full": [...ALL fixture objects...],
  "value_bets": [...EDGE fixtures only...]
}"""


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
    instruction = (
        "Return ONLY valid JSON, no markdown fences, this schema:\n"
        f"{OUTPUT_SCHEMA}\n\n"
        f"Each fixture object:\n{FIXTURE_SCHEMA}\n\n"
        "EVERY fixture object in EVERY array (top_picks, strong_fades, "
        "double_chances, avoid_list, fixtures_full) MUST include every field in "
        "the schema above, including betting_category, pundit_take and "
        "pundit_action. fixtures_full MUST contain ALL fixtures. Assign each "
        "fixture to exactly one of top_picks / strong_fades / double_chances / "
        "avoid_list according to its pre-computed betting_category. "
        "Do NOT include a telegram_message field - it is built separately."
    )
    return "\n\n".join(["\n\n".join(blocks), perf_block, instruction])


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
            raise SystemExit("[strategy] OPENAI_API_KEY not set in environment / .env")
        _CLIENT = OpenAI(api_key=api_key)
    return _CLIENT


def call_gpt(user_prompt: str, extra: str | None = None) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    if extra:
        messages.append({"role": "user", "content": extra})
    resp = _openai_client().chat.completions.create(
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
            "pundit_take": f"Model probability: {fx['prob_homewin']:.0%}. No AI analysis available.",
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
                fx["stake_advice"] = "Small"  # never Skip for double_chance
                if not fx.get("bet_type") or fx.get("bet_type") == "Skip":
                    fx["bet_type"] = "Back Double Chance (X2)"
                fx["pundit_action"] = "Back Double Chance (X2)"


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
    injury_words = ("injury", "injured", "knee", "hamstring", "ruled out",
                    "doubt", "unavailable", "setback", "sidelined")
    injuries: list[str] = []
    try:
        import json as _json
        import pathlib as _pathlib

        ctx = _json.loads(_pathlib.Path("artifacts/match_context.json").read_text())
        all_teams = set()
        for fx in ctx.get("fixtures", []):
            all_teams.add(fx.get("home_team", ""))
            all_teams.add(fx.get("away_team", ""))
        for fix in ctx.get("fixtures", []):
            for is_home, feed in ((True, fix.get("home_news", [])),
                                  (False, fix.get("away_news", []))):
                hit = None
                for news in feed:
                    headline = news if isinstance(news, str) else news.get("headline", "")
                    if any(w in headline.lower() for w in injury_words):
                        hit = headline
                        break
                if hit:
                    team = fix["home_team"] if is_home else fix["away_team"]
                    detail = _extract_injury_detail(hit, team, all_teams)
                    injuries.append(f"{team} \u2014 {detail}" if detail
                                    else f"{team} \u2014 {hit[:60]}")
                    break  # one line per fixture
    except Exception:
        pass
    lines += injuries[:3] if injuries else ["None reported."]

    lines.append("")
    lines.append("Full analysis: shab00.github.io/football")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--debug",
        action="store_true",
        help="print the raw GPT response before parsing",
    )
    args = parser.parse_args()

    load_dotenv()

    if not CONTEXT_JSON.exists():
        raise SystemExit(f"[strategy] missing {CONTEXT_JSON} - run compute_context.py first")
    context = json.loads(CONTEXT_JSON.read_text(encoding="utf-8"))
    fixtures = context.get("fixtures", [])

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
        if args.debug:
            print("=" * 72)
            print("[strategy] RAW GPT RESPONSE:")
            print(raw)
            print("=" * 72)
        try:
            data = extract_json(raw, allow_llm_repair=False)
        except Exception:
            raw = call_gpt(user_prompt, extra="Return only valid JSON")
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

    # model_form is ALWAYS built from match_context.json - never GPT, never stale.
    perf = context.get("model_performance", {})
    data["model_form"] = (
        f"Model is {perf.get('streak_label', '')} \u2014 "
        f"{perf.get('overall_accuracy_pct', 0)}% accuracy "
        f"over last {perf.get('total_predictions', 0)} confident predictions. "
        f"EDGE profit: {perf.get('edge_profit', 0):+.2f} units."
    )

    # Guarantee the rest-of-card paragraph carries the real accuracy figure
    # (gpt-4o-mini often paraphrases the model stats away).
    _acc = perf.get("overall_accuracy_pct")
    _para = (data.get("rest_of_card_paragraph") or "").strip()
    if _acc is not None and f"{_acc}%" not in _para:
        _sfx = (f" The model is {perf.get('streak_label', '')} at {_acc}% "
                f"accuracy over the last {perf.get('total_predictions', 0)} "
                f"confident predictions.")
        data["rest_of_card_paragraph"] = (_para + _sfx).strip()

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


if __name__ == "__main__":
    main()
