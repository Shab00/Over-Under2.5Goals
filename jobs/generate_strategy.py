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

import glob
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

CONTEXT_JSON = Path("artifacts/match_context.json")
ARCHIVE_DIR = Path("artifacts/strategy_archive")
LATEST_JSON = Path("artifacts/strategy_latest.json")
LATEST_MD = Path("artifacts/strategy_latest.md")
FAISS_INDEX = Path("artifacts/strategy_faiss.index")

MODEL = "gpt-4o-mini"
EMBED_MODEL = "text-embedding-3-small"
MAX_TOKENS = 2500
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
    "- Always reference injury news if headlines mention key players out\n"
    "- If RAG shows the model was wrong in similar past situations acknowledge "
    "it and reduce confidence\n"
    "- Write pundit_take as natural spoken pundit language"
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
  "pundit_take": "2-3 sentence analysis",
  "bet_type": "Back Home|Lay Home|Skip",
  "stake_advice": "Banker|Value Bet|Small|Skip",
  "rag_informed": true/false
}"""

OUTPUT_SCHEMA = """{
  "generated_at": "ISO datetime",
  "model_form": "one sentence on recent model form",
  "gameweek_summary": "2-3 sentence pundit overview",
  "top_picks": [...3-5 fixture objects...],
  "fixtures_full": [...all fixture objects...],
  "value_bets": [...EDGE fixtures only...],
  "avoid_list": [...Avoid or Low confidence...],
  "telegram_message": "150 word max punchy HTML summary, header: <b>EPL AI Pundit Strategy</b>, top picks with <b>Home vs Away</b> bold, one key insight, footer: Full analysis: shab00.github.io/football"
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
        "Model performance context:\n"
        f"Overall accuracy last 30: {perf.get('overall_accuracy_pct')}%\n"
        f"EDGE accuracy: {perf.get('edge_accuracy_pct')}% "
        f"({perf.get('edge_profit', 0):+.2f} units profit)\n"
        f"Current streak: {perf.get('streak_label')} ({perf.get('streak_string')})"
    )
    instruction = (
        "Return ONLY valid JSON, no markdown fences, this schema:\n"
        f"{OUTPUT_SCHEMA}\n\n"
        f"Each fixture object:\n{FIXTURE_SCHEMA}"
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


def extract_json(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t.strip())
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1 and end > start:
        t = t[start:end + 1]
    return json.loads(t)


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
    parts += ["", "## Value Bets (EDGE)"]
    parts += [_fx_md(fx) for fx in data.get("value_bets", [])]
    parts += ["", "## Avoid This Week"]
    for fx in data.get("avoid_list", []):
        reason = fx.get("pundit_take") or fx.get("reason") or ""
        parts.append(f"- **{fx.get('home_team')} vs {fx.get('away_team')}** - {reason}")
    parts += ["", "## Model Form", data.get("model_form", ""), ""]
    return "\n".join(parts)


def main() -> None:
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
    try:
        raw = call_gpt(user_prompt)
    except Exception as exc:  # noqa: BLE001 - surface a clean message, not a stack trace
        raise SystemExit(f"[strategy] GPT call failed: {exc}")
    try:
        data = extract_json(raw)
    except Exception:
        raw = call_gpt(user_prompt, extra="Return only valid JSON")
        data = extract_json(raw)

    data.setdefault("generated_at", datetime.now(timezone.utc).isoformat())

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
    n_edge = len(data.get("value_bets", []))
    n_fx = len(data.get("fixtures_full", fixtures))
    print(
        f"[strategy] {n_fx} fixtures | {n_top} top picks | "
        f"{n_edge} value bets | RAG: {n_rag} matches retrieved"
    )
    print(f"[strategy] wrote {LATEST_JSON}")


if __name__ == "__main__":
    main()
