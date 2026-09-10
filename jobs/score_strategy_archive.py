#!/usr/bin/env python3
"""Score unscored archived strategies against actual results.

Walks ``artifacts/strategy_archive/*.json`` for entries with ``scored == false``,
matches every fixture in ``fixtures_full`` to ``data/processed/results_merged.csv``
by home team + away team + kickoff date, and - once every fixture in a strategy
has a final result - stamps ``scored: true`` plus a ``score_summary`` block and
rewrites the file in place.
"""

from __future__ import annotations

import glob
import json
import re
from pathlib import Path

import pandas as pd

ARCHIVE_DIR = Path("artifacts/strategy_archive")
RESULTS_CSV = Path("data/processed/results_merged.csv")


def _norm(s: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def load_results_lookup() -> dict:
    if not RESULTS_CSV.exists():
        return {}
    df = pd.read_csv(RESULTS_CSV)
    lookup: dict = {}
    for _, r in df.iterrows():
        ftr = str(r.get("FTR", "")).strip()
        if not ftr or ftr.lower() == "nan":
            continue
        date = str(r.get("kickoff_time_utc", ""))[:10]
        home = str(r.get("home_team", ""))
        away = str(r.get("away_team", ""))
        lookup[(_norm(home), _norm(away), date)] = ftr
    return lookup


def find_ftr(lookup: dict, fx: dict) -> str | None:
    date = str(fx.get("kickoff", ""))[:10]
    return lookup.get((_norm(fx.get("home_team")), _norm(fx.get("away_team")), date))


def score_fixture(fx: dict, ftr: str) -> dict:
    fx = dict(fx)
    signal = fx.get("signal")
    bet_type = fx.get("bet_type")
    correct = (signal == "Home" and ftr == "H") or (
        signal == "Not Home" and ftr in ("A", "D")
    )
    try:
        odds = float(fx.get("odds", 0) or 0)
    except (TypeError, ValueError):
        odds = 0.0
    if bet_type == "Back Home":
        profit = (odds - 1) if correct else -1
    else:
        profit = 0
    fx["correct"] = bool(correct)
    fx["FTR"] = ftr
    fx["profit"] = round(float(profit), 2)
    return fx


def main() -> None:
    lookup = load_results_lookup()

    scored_now = 0
    pending = 0

    for path in sorted(glob.glob(str(ARCHIVE_DIR / "*.json"))):
        p = Path(path)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"[score] skip unreadable {p.name}: {exc}")
            continue

        if data.get("scored") is not False:
            continue

        fixtures = data.get("fixtures_full", [])
        scored_fixtures = []
        all_have_ftr = bool(fixtures)
        for fx in fixtures:
            ftr = find_ftr(lookup, fx)
            if ftr is None:
                all_have_ftr = False
                scored_fixtures.append(fx)
            else:
                scored_fixtures.append(score_fixture(fx, ftr))

        if not all_have_ftr:
            pending += 1
            continue

        total = len(scored_fixtures)
        correct = sum(1 for fx in scored_fixtures if fx.get("correct"))
        total_profit = round(sum(float(fx.get("profit", 0)) for fx in scored_fixtures), 2)
        edge = [fx for fx in scored_fixtures if fx.get("edge_label") == "EDGE"]
        edge_correct = sum(1 for fx in edge if fx.get("correct"))
        edge_profit = round(sum(float(fx.get("profit", 0)) for fx in edge), 2)

        data["fixtures_full"] = scored_fixtures
        data["scored"] = True
        data["score_summary"] = {
            "total": total,
            "correct": correct,
            "accuracy_pct": round(correct / total * 100, 1) if total else 0.0,
            "total_profit": total_profit,
            "edge_correct": edge_correct,
            "edge_profit": edge_profit,
        }
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        scored_now += 1

    print(f"[score] {scored_now} strategies scored, {pending} pending")


if __name__ == "__main__":
    main()
