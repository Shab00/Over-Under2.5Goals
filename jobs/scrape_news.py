#!/usr/bin/env python3
"""Scrape Premier League injury / team-news headlines from NewsNow.

For every fixture in the upcoming gameweek (kickoff within the next 7 days,
read from ``data/processed/updated_fixtures_with_odds.csv``) this builds the
NewsNow "Injuries and Suspensions" URLs for both clubs, scrapes the recent
headlines, and also grabs the league-wide PL injuries page.

The result is written to ``data/processed/news_context.json`` as a *cumulative*
knowledge base for the downstream RAG agent: existing headlines are kept
forever, only genuinely new headline strings are appended, and every entry
carries a ``first_seen`` timestamp.

Only libraries already in requirements.txt are used: requests, bs4,
pandas, python-dateutil.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

BASE_URL = "https://www.newsnow.co.uk/h/Sport/Football/Premier+League"
GENERAL_PL_INJURIES_URL = f"{BASE_URL}/Injuries+and+Suspensions"

DEFAULT_FIXTURES_CSV = "data/processed/updated_fixtures_with_odds.csv"
DEFAULT_OUT_JSON = "data/processed/news_context.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Team display name -> NewsNow URL slug (as supplied in the spec).
TEAM_NAME_MAP = {
    "Arsenal": "Arsenal",
    "Aston Villa": "Aston+Villa",
    "Bournemouth": "Bournemouth",
    "Brentford": "Brentford",
    "Brighton": "Brighton",
    "Chelsea": "Chelsea",
    "Coventry City": "Coventry+City",
    "Crystal Palace": "Crystal+Palace",
    "Everton": "Everton",
    "Fulham": "Fulham",
    "Hull City": "Hull+City",
    "Ipswich Town": "Ipswich+Town",
    "Leeds": "Leeds+United",
    "Liverpool": "Liverpool",
    "Man City": "Manchester+City",
    "Man United": "Manchester+United",
    "Newcastle": "Newcastle+United",
    "Nottm Forest": "Nottingham+Forest",
    "Sunderland": "Sunderland",
    "Tottenham": "Tottenham+Hotspur",
}


def _norm(s: str) -> str:
    """Lower-case and strip every non-alphanumeric char for tolerant matching."""
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


# Primary lookup keyed by the normalised spec name.
_NEWSNOW_BY_NORM = {_norm(k): v for k, v in TEAM_NAME_MAP.items()}

# Extra aliases for name variants that show up in the fixtures / odds feed
# (e.g. "Nott'm Forest", "Manchester City", "Ipswich").
_ALIAS_BY_NORM = {
    _norm("Nott'm Forest"): "Nottingham+Forest",
    _norm("Nottingham Forest"): "Nottingham+Forest",
    _norm("Spurs"): "Tottenham+Hotspur",
    _norm("Tottenham Hotspur"): "Tottenham+Hotspur",
    _norm("Manchester City"): "Manchester+City",
    _norm("Manchester United"): "Manchester+United",
    _norm("Man Utd"): "Manchester+United",
    _norm("Newcastle United"): "Newcastle+United",
    _norm("Leeds United"): "Leeds+United",
    _norm("Brighton and Hove Albion"): "Brighton",
    _norm("Brighton & Hove Albion"): "Brighton",
    _norm("AFC Bournemouth"): "Bournemouth",
    _norm("Ipswich"): "Ipswich+Town",
    _norm("Coventry"): "Coventry+City",
    _norm("Hull"): "Hull+City",
}


def resolve_newsnow_team(name: str) -> str | None:
    """Return the NewsNow URL slug for a team name, or ``None`` if unknown."""
    key = _norm(name)
    return _NEWSNOW_BY_NORM.get(key) or _ALIAS_BY_NORM.get(key)


def team_injuries_url(newsnow_slug: str) -> str:
    return f"{BASE_URL}/{newsnow_slug}/Injuries+and+Suspensions"


# --------------------------------------------------------------------------- #
# Time parsing
# --------------------------------------------------------------------------- #

_REL_WORDS_RE = re.compile(
    r"(\d+)\s*(second|sec|minute|min|hour|hr|day|week)s?\s*(?:ago)?", re.I
)
_COMPACT_RE = re.compile(r"^\s*(\d+)\s*([smhdw])\s*$", re.I)
_CLOCK_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*$")


def parse_relative_time(raw: str, now: datetime) -> tuple[datetime | None, bool]:
    """Best-effort parse of a NewsNow time label into an absolute UTC datetime.

    Handles ``"2h"``, ``"35m"``, ``"1d"``, ``"3w"``, ``"14:30"``,
    ``"2 hours ago"``, ``"just now"`` and finally falls back to
    ``dateutil`` fuzzy parsing. Returns ``(datetime, True)`` on success or
    ``(None, False)`` when nothing could be interpreted.
    """
    if not raw:
        return None, False
    s = str(raw).strip()
    low = s.lower()

    if low in {"now", "just now", "just in", "moments ago", "live"}:
        return now, True

    m = _COMPACT_RE.match(s)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        delta = {
            "s": timedelta(seconds=n),
            "m": timedelta(minutes=n),
            "h": timedelta(hours=n),
            "d": timedelta(days=n),
            "w": timedelta(weeks=n),
        }[unit]
        return now - delta, True

    m = _REL_WORDS_RE.search(low)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("sec"):
            delta = timedelta(seconds=n)
        elif unit.startswith("min"):
            delta = timedelta(minutes=n)
        elif unit.startswith(("hour", "hr")):
            delta = timedelta(hours=n)
        elif unit.startswith("day"):
            delta = timedelta(days=n)
        elif unit.startswith("week"):
            delta = timedelta(weeks=n)
        else:
            delta = None
        if delta is not None:
            return now - delta, True

    m = _CLOCK_RE.match(s)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        if 0 <= hh < 24 and 0 <= mm < 60:
            cand = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if cand > now:  # clock time in the "future" means it was yesterday
                cand -= timedelta(days=1)
            return cand, True

    # Last resort: fuzzy parse (covers "Mon 14:30", "8 Sep", ISO strings...).
    try:
        from dateutil import parser as dtparser

        dt = dtparser.parse(s, fuzzy=True, default=now)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc), True
    except Exception:
        return None, False


# --------------------------------------------------------------------------- #
# Scraping
# --------------------------------------------------------------------------- #

_CONTAINER_SELECTOR = ",".join(
    [
        "div.hl",
        "div.hl-hidden",
        "article.hn",
        "article",
        "div.article",
        "li.hl",
        "div.newsfeed-item",
    ]
)
_TIME_TOKEN_RE = re.compile(
    r"\b(\d+\s*[smhdw]|\d{1,2}:\d{2}|\d+\s*(?:minute|hour|day|week)s?\s*ago)\b",
    re.I,
)


def fetch_html(url: str, timeout: float = 5.0) -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def extract_headlines(
    html: str,
    *,
    team: str,
    url: str,
    now: datetime,
    window_hours: int,
    keep_unknown_time: bool,
) -> list[dict]:
    """Pull every article headline out of a NewsNow page.

    Only headlines whose parsed timestamp is within ``window_hours`` are
    returned. Headlines whose time label cannot be parsed are kept when
    ``keep_unknown_time`` is True (default) so a NewsNow markup change does
    not silently empty the feed; pass ``--strict-time`` to drop them.
    """
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    seen_local: set[str] = set()

    for container in soup.select(_CONTAINER_SELECTOR):
        anchor = (
            container.select_one("a.hll")
            or container.select_one("a.hl-title")
            or container.find("a", href=True)
        )
        if anchor is None:
            continue

        headline = anchor.get_text(" ", strip=True)
        if not headline or len(headline) < 12:
            continue

        key = headline.lower()
        if key in seen_local:
            continue
        seen_local.add(key)

        # Source label.
        src_el = container.select_one(".src, .src-part, .source, .hl-source")
        source = src_el.get_text(" ", strip=True) if src_el else ""

        # Time label.
        time_el = container.select_one(
            ".time, .datetime, .date, .hl-date, time, .hl-time"
        )
        time_raw = ""
        if time_el is not None:
            time_raw = (
                time_el.get("datetime")
                or time_el.get("title")
                or time_el.get_text(" ", strip=True)
            )
        if not time_raw:
            m = _TIME_TOKEN_RE.search(container.get_text(" ", strip=True))
            if m:
                time_raw = m.group(1)
        time_raw = (time_raw or "").strip()

        ts, ok = parse_relative_time(time_raw, now)
        if ok and ts is not None:
            age_hours = (now - ts).total_seconds() / 3600.0
            if age_hours < -1 or age_hours > window_hours:
                continue
        elif not keep_unknown_time:
            continue

        out.append(
            {
                "headline": headline,
                "source": source,
                "time_ago": time_raw or "unknown",
                "team": team,
                "url": url,
            }
        )

    return out


def scrape_url(
    url: str,
    *,
    team: str,
    now: datetime,
    window_hours: int,
    timeout: float,
    keep_unknown_time: bool,
) -> list[dict]:
    """Fetch + parse a single NewsNow page, tolerating network failures."""
    try:
        html = fetch_html(url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - one bad page must not abort the run
        print(f"[news] warn: fetch failed for {url}: {exc}")
        return []
    try:
        return extract_headlines(
            html,
            team=team,
            url=url,
            now=now,
            window_hours=window_hours,
            keep_unknown_time=keep_unknown_time,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[news] warn: parse failed for {url}: {exc}")
        return []


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

_KICKOFF_COLS = ("kickoff_time_utc", "Kickoff", "kickoff", "Date", "date")


def load_upcoming_fixtures(csv_path: Path, days: int, now: datetime) -> list[dict]:
    """Return fixtures with kickoff between the start of today (UTC) and now+days."""
    if not csv_path.exists():
        print(f"[news] fixtures CSV not found: {csv_path}")
        return []

    try:
        df = pd.read_csv(csv_path)
    except pd.errors.EmptyDataError:
        print(f"[news] fixtures CSV is empty: {csv_path}")
        return []

    df = df.dropna(how="all")
    if df.empty:
        return []

    kickoff_col = next((c for c in _KICKOFF_COLS if c in df.columns), None)
    if kickoff_col is None:
        print(
            f"[news] no kickoff column in {csv_path} "
            f"(looked for {', '.join(_KICKOFF_COLS)})"
        )
        return []

    if "home_team" in df.columns:
        home_col, away_col = "home_team", "away_team"
    elif "HomeTeam" in df.columns:
        home_col, away_col = "HomeTeam", "AwayTeam"
    else:
        print(f"[news] no home/away team columns in {csv_path}")
        return []

    kicks = pd.to_datetime(df[kickoff_col], utc=True, errors="coerce")
    window_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_end = now + timedelta(days=days)
    mask = kicks.notna() & (kicks >= window_start) & (kicks <= window_end)

    fixtures: list[dict] = []
    for idx in df.index[mask]:
        home = str(df.at[idx, home_col]).strip()
        away = str(df.at[idx, away_col]).strip()
        if not home or not away or home.lower() == "nan" or away.lower() == "nan":
            continue
        fixtures.append(
            {
                "home_team": home,
                "away_team": away,
                "kickoff": kicks[idx].isoformat(),
            }
        )

    fixtures.sort(key=lambda f: (f["kickoff"], f["home_team"]))
    return fixtures


# --------------------------------------------------------------------------- #
# Dedup / merge helpers
# --------------------------------------------------------------------------- #


def _fixture_key(fx: dict) -> tuple[str, str, str]:
    return (
        _norm(fx.get("home_team", "")),
        _norm(fx.get("away_team", "")),
        str(fx.get("kickoff", "")),
    )


def load_existing(out_path: Path) -> dict:
    if not out_path.exists():
        return {}
    try:
        with out_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except Exception as exc:  # noqa: BLE001
        print(f"[news] warn: could not read existing {out_path}: {exc}")
    return {}


def collect_seen(existing: dict) -> tuple[set[str], dict[str, str]]:
    """Build the set of already-seen headline strings + their first_seen map."""
    seen: set[str] = set()
    first_seen: dict[str, str] = {}

    def _ingest(entries) -> None:
        for h in entries or []:
            text = h.get("headline")
            if not text:
                continue
            seen.add(text)
            if h.get("first_seen") and text not in first_seen:
                first_seen[text] = h["first_seen"]

    for fx in existing.get("fixtures", []):
        _ingest(fx.get("home_news"))
        _ingest(fx.get("away_news"))
    _ingest(existing.get("general_pl_news"))

    return seen, first_seen


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixtures-csv", default=DEFAULT_FIXTURES_CSV)
    ap.add_argument("--out", default=DEFAULT_OUT_JSON)
    ap.add_argument("--days", type=int, default=7, help="Fixture look-ahead window")
    ap.add_argument(
        "--window-hours",
        type=int,
        default=48,
        help="Keep only headlines newer than this many hours",
    )
    ap.add_argument("--timeout", type=float, default=5.0, help="Per-request timeout (s)")
    ap.add_argument(
        "--sleep",
        type=float,
        default=1.0,
        help="Politeness delay between NewsNow requests (s)",
    )
    ap.add_argument(
        "--strict-time",
        action="store_true",
        help="Drop headlines whose time label cannot be parsed",
    )
    return ap


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def main() -> None:
    args = build_arg_parser().parse_args()

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    out_path = Path(args.out)
    keep_unknown_time = not args.strict_time

    fixtures = load_upcoming_fixtures(Path(args.fixtures_csv), args.days, now)

    # --- OFF-SEASON GUARD ----------------------------------------------------
    if not fixtures:
        empty = {"scraped_at": now_iso, "fixtures": [], "general_pl_news": []}
        write_json(out_path, empty)
        print(
            "[news] no fixtures in the next "
            f"{args.days} days (off-season?) - wrote empty structure"
        )
        print(f"[news] wrote {out_path}")
        sys.exit(0)

    existing = load_existing(out_path)
    seen, first_seen_map = collect_seen(existing)

    stats = {"new": 0, "already_seen": 0}

    def take(raw_entries: list[dict]) -> list[dict]:
        """Filter a freshly scraped batch against the global seen-set."""
        kept: list[dict] = []
        for entry in raw_entries:
            text = entry["headline"]
            if text in seen:
                stats["already_seen"] += 1
                continue
            seen.add(text)
            stats["new"] += 1
            entry = dict(entry)
            entry["first_seen"] = first_seen_map.get(text, now_iso)
            kept.append(entry)
        return kept

    # --- Per-fixture team news --------------------------------------------
    fresh_fixtures: list[dict] = []
    for fx in fixtures:
        fx_out = {
            "home_team": fx["home_team"],
            "away_team": fx["away_team"],
            "kickoff": fx["kickoff"],
            "home_news": [],
            "away_news": [],
        }
        for side, team_name in (("home_news", fx["home_team"]), ("away_news", fx["away_team"])):
            slug = resolve_newsnow_team(team_name)
            if slug is None:
                print(f"[news] warn: no NewsNow mapping for team '{team_name}' - skipping")
                continue
            url = team_injuries_url(slug)
            batch = scrape_url(
                url,
                team=team_name,
                now=now,
                window_hours=args.window_hours,
                timeout=args.timeout,
                keep_unknown_time=keep_unknown_time,
            )
            fx_out[side] = take(batch)
            if args.sleep:
                time.sleep(args.sleep)
        fresh_fixtures.append(fx_out)

    # --- League-wide PL injuries page -----------------------------------
    general_batch = scrape_url(
        GENERAL_PL_INJURIES_URL,
        team="Premier League",
        now=now,
        window_hours=args.window_hours,
        timeout=args.timeout,
        keep_unknown_time=keep_unknown_time,
    )
    fresh_general = take(general_batch)

    # --- Merge with existing cumulative knowledge base ------------------
    fixtures_by_key: "OrderedDict[tuple[str, str, str], dict]" = OrderedDict()
    for fx in existing.get("fixtures", []):
        fx.setdefault("home_news", [])
        fx.setdefault("away_news", [])
        fixtures_by_key[_fixture_key(fx)] = fx

    for fx in fresh_fixtures:
        key = _fixture_key(fx)
        if key in fixtures_by_key:
            prev = fixtures_by_key[key]
            prev["home_news"].extend(fx["home_news"])
            prev["away_news"].extend(fx["away_news"])
            prev["kickoff"] = fx["kickoff"]
        else:
            fixtures_by_key[key] = fx

    general_news = list(existing.get("general_pl_news", []))
    general_news.extend(fresh_general)

    payload = {
        "scraped_at": now_iso,
        "fixtures": list(fixtures_by_key.values()),
        "general_pl_news": general_news,
    }
    write_json(out_path, payload)

    # --- Summary --------------------------------------------------------
    print(
        f"[news] {stats['new']} new headlines, "
        f"{stats['already_seen']} already seen, skipped"
    )
    print(
        f"[news] scraped {stats['new']} new headlines for "
        f"{len(fresh_fixtures)} fixtures"
    )
    print(f"[news] wrote {out_path}")


if __name__ == "__main__":
    main()
