from __future__ import annotations

import argparse
import csv
import io
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
import sys

EPL_2526_URL = "https://www.football-data.co.uk/mmz4281/2526/E0.csv"


@dataclass(frozen=True)
class Paths:
    raw_csv: Path
    input_combined_csv: Path
    output_combined_csv: Path
    fixtures_csv: Path


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _utc_today_date():
    return datetime.now(timezone.utc).date()


def download_csv(url: str, timeout_sec: int = 30) -> bytes:
    resp = requests.get(url, timeout=timeout_sec)
    resp.raise_for_status()
    return resp.content


def _parse_football_data_date(s: str) -> Optional[datetime.date]:
    if s is None:
        return None
    s = str(s).strip()
    if not s or s.lower() == "nan":
        return None

    for fmt in ("%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _normalize_team_col(df: pd.DataFrame, col: str) -> None:
    if col in df.columns:
        df[col] = df[col].astype(str).str.strip()


def ensure_match_key(df: pd.DataFrame, default_div: str = "E0") -> pd.DataFrame:
    df = df.copy()

    if "Date" not in df.columns:
        raise ValueError(f"Expected a 'Date' column but got columns: {list(df.columns)}")

    if "HomeTeam" not in df.columns or "AwayTeam" not in df.columns:
        raise ValueError(
            "Expected 'HomeTeam' and 'AwayTeam' columns. "
            f"Columns: {list(df.columns)}"
        )

    if "Div" not in df.columns:
        df["Div"] = default_div

    _normalize_team_col(df, "HomeTeam")
    _normalize_team_col(df, "AwayTeam")
    df["Div"] = df["Div"].astype(str).str.strip()

    if "DateISO" not in df.columns:
        df["DateParsed"] = df["Date"].apply(_parse_football_data_date)
        df["DateISO"] = df["DateParsed"].apply(lambda d: d.isoformat() if pd.notna(d) else None)
    else:
        if "DateParsed" not in df.columns:
            df["DateParsed"] = pd.to_datetime(df["DateISO"], errors="coerce").dt.date

    if "match_key" not in df.columns:
        df["match_key"] = (
            df["Div"]
            + "|"
            + df["DateISO"].astype(str)
            + "|"
            + df["HomeTeam"]
            + "|"
            + df["AwayTeam"]
        )

    return df


def normalize_new_scrape(df: pd.DataFrame) -> pd.DataFrame:
    df = ensure_match_key(df, default_div="E0").copy()
    df["scraped_at_utc"] = datetime.now(timezone.utc).isoformat()
    return df


def upsert_by_match_key(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    merged = pd.concat([existing, new], ignore_index=True, sort=False)

    if "scraped_at_utc" not in merged.columns:
        merged["scraped_at_utc"] = None

    merged = merged.sort_values(by=["match_key", "scraped_at_utc"], kind="stable")
    merged = merged.drop_duplicates(subset=["match_key"], keep="last").reset_index(drop=True)
    return merged


def write_csv(df: pd.DataFrame, path: Path) -> None:
    _ensure_parent(path)
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def build_next_fixtures(df: pd.DataFrame, days: int) -> pd.DataFrame:
    today = _utc_today_date()
    end = today + timedelta(days=days)

    if "DateParsed" not in df.columns:
        df = ensure_match_key(df)
    df["DateParsed"] = pd.to_datetime(df["DateParsed"], errors="coerce").dt.date
    mask = (df["DateParsed"].notna()) & (df["DateParsed"] >= today) & (df["DateParsed"] <= end)
    out = df.loc[mask].copy()

    prefer = ["match_key", "Div", "DateISO", "HomeTeam", "AwayTeam"]
    prefer_present = [c for c in prefer if c in out.columns]
    out = out[prefer_present + [c for c in out.columns if c not in prefer_present]]

    out = out.sort_values(by=["DateISO", "HomeTeam", "AwayTeam"], kind="stable").reset_index(drop=True)
    return out


def backup_file(path: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    bak = path.with_suffix(path.suffix + f".bak-{ts}")
    shutil.copy2(path, bak)
    return bak


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=EPL_2526_URL)
    ap.add_argument("--input-combined-csv", default="data/processed/combinedWithOdds.csv")
    ap.add_argument(
        "--output-combined-csv",
        default="data/processed/combinedWithOdds.upserted.csv",
        help="Staged output combined CSV (ignored when --in-place is set)",
    )
    ap.add_argument("--raw-csv", default="data/raw/football_data/E0_2526.csv")
    ap.add_argument("--fixtures-csv", default="data/processed/fixtures_next7d.csv")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--backup-input", action="store_true", help="Make a timestamped backup of input combined CSV")
    ap.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite input combined CSV (writes to temp file then replaces). Implies --backup-input.",
    )
    args = ap.parse_args()

    paths = Paths(
        raw_csv=Path(args.raw_csv),
        input_combined_csv=Path(args.input_combined_csv),
        output_combined_csv=Path(args.output_combined_csv),
        fixtures_csv=Path(args.fixtures_csv),
    )

    if args.in_place:
        args.backup_input = True
        combined_write_path = paths.input_combined_csv
    else:
        combined_write_path = paths.output_combined_csv

    if args.backup_input and paths.input_combined_csv.exists():
        bak = backup_file(paths.input_combined_csv)
        print(f"[scrape_matches] backed up input_combined_csv to {bak}")

    # Load new scrape
    if args.no_download:
        if not paths.raw_csv.exists():
            raise SystemExit(f"--no-download set but raw file not found: {paths.raw_csv}")
        raw_bytes = paths.raw_csv.read_bytes()
        source = f"local:{paths.raw_csv}"
    else:
        raw_bytes = download_csv(args.url)
        _ensure_parent(paths.raw_csv)
        paths.raw_csv.write_bytes(raw_bytes)
        source = args.url

    df_new = pd.read_csv(io.BytesIO(raw_bytes))
    df_new = df_new.dropna(how="all")
    df_new = normalize_new_scrape(df_new)

    if paths.input_combined_csv.exists():
        df_existing = pd.read_csv(paths.input_combined_csv)
        df_existing = df_existing.dropna(how="all")
        df_existing = ensure_match_key(df_existing, default_div="E0")
    else:
        df_existing = pd.DataFrame(columns=df_new.columns)

    combined = upsert_by_match_key(df_existing, df_new)

    if args.in_place:
        tmp_path = combined_write_path.with_suffix(combined_write_path.suffix + ".tmp")
        write_csv(combined, tmp_path)
        tmp_path.replace(combined_write_path)
    else:
        write_csv(combined, combined_write_path)

    fixtures = build_next_fixtures(combined, days=args.days)
    write_csv(fixtures, paths.fixtures_csv)

    today = _utc_today_date()
    end = today + timedelta(days=args.days)

    print(f"[scrape_matches] source={source}")
    print(f"[scrape_matches] input_combined_csv={paths.input_combined_csv}")
    print(f"[scrape_matches] combined_write_csv={combined_write_path} rows={len(combined)}")
    print(f"[scrape_matches] fixtures_csv={paths.fixtures_csv} window_utc={today.isoformat()}..{end.isoformat()} rows={len(fixtures)}")

    # --- OFF-SEASON GUARD ---
    if len(fixtures) == 0:
        print(f"[scrape_matches][INFO] No fixtures found for the current window (off-season likely). Exiting and writing empty fixtures file: {paths.fixtures_csv}")
        Path(paths.fixtures_csv).parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame().to_csv(paths.fixtures_csv, index=False)
        sys.exit(0)

if __name__ == "__main__":
    main()
