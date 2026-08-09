#!/usr/bin/env python3
import csv
import datetime
from pathlib import Path
import sys

# ---------- CONFIG ----------
SNAPSHOT_CSV = Path("snapshots/predictions_latest.csv")
OUTPUT_DIR = Path("football")
OUTPUT_FILE = OUTPUT_DIR / "index.html"
TELEGRAM_CHANNEL_LINK = "https://t.me/HomeWinPrediction"
PORTFOLIO_URL = "/"

# ---------- HTML TEMPLATE ----------
PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Premier League Home‑Win Predictions</title>
  <style>
    :root {{
      --bg: #0f172a;
      --panel: #111827;
      --panel-border: #1f2937;
      --text: #e5e7eb;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --accent-hover: #0ea5e9;
      --button-text: #082f49;
      --shadow: 0 20px 40px rgba(0, 0, 0, 0.25);
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: Arial, Helvetica, sans-serif;
      background: radial-gradient(circle at top, rgba(56,189,248,0.12), transparent 30%),
                  linear-gradient(180deg, #020617 0%, #0f172a 100%);
      color: var(--text);
      min-height: 100vh;
      padding: 2rem 0;
    }}
    .container {{
      width: min(960px, calc(100% - 2rem));
      margin: 0 auto;
    }}
    h1 {{
      font-size: clamp(1.8rem, 4vw, 3rem);
      margin-bottom: 0.5rem;
    }}
    .updated {{
      color: var(--muted);
      font-size: 0.95rem;
      margin-bottom: 0.25rem;
    }}
    .refresh-note {{
      color: var(--muted);
      font-size: 0.85rem;
      margin-bottom: 1rem;
      font-style: italic;
    }}
    .top-actions {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 1rem;
      margin-bottom: 1.5rem;
    }}
    .telegram-banner {{
      background: rgba(56,189,248,0.1);
      border: 1px solid var(--accent);
      border-radius: 12px;
      padding: 0.8rem 1.2rem;
      font-size: 0.95rem;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
    }}
    .telegram-banner a {{
      color: var(--accent);
      font-weight: 700;
      text-decoration: none;
    }}
    .telegram-banner a:hover {{
      text-decoration: underline;
    }}
    .back-button {{
      display: inline-block;
      color: var(--accent);
      border: 1px solid var(--accent);
      border-radius: 12px;
      padding: 0.8rem 1.2rem;
      font-size: 0.95rem;
      font-weight: 600;
      text-decoration: none;
      transition: background 0.2s, color 0.2s;
    }}
    .back-button:hover {{
      background: var(--accent);
      color: var(--button-text);
      text-decoration: none;
    }}
    .performance-tracker {{
      background: rgba(17,24,39,0.8);
      border: 1px solid var(--panel-border);
      border-radius: 16px;
      padding: 1.5rem;
      margin-bottom: 1.5rem;
      box-shadow: var(--shadow);
    }}
    .performance-tracker h2 {{
      font-size: 1.2rem;
      margin-bottom: 0.8rem;
      color: var(--accent);
    }}
    .performance-summary {{
      display: flex;
      gap: 2rem;
      flex-wrap: wrap;
      margin-bottom: 1rem;
    }}
    .performance-stat {{
      font-size: 1rem;
    }}
    .performance-stat strong {{
      color: var(--accent);
    }}
    .table-wrapper {{
      max-width: 100%;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
    }}
    .predictions-table {{
      width: 100%;
      border-collapse: collapse;
      background: rgba(17,24,39,0.9);
      border: 1px solid var(--panel-border);
      border-radius: 16px;
      overflow: hidden;
      box-shadow: var(--shadow);
      min-width: 600px;
    }}
    th, td {{
      padding: 0.9rem 1.2rem;
      text-align: left;
      border-bottom: 1px solid var(--panel-border);
      white-space: nowrap;
    }}
    th {{
      background: #0f172a;
      font-weight: 700;
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      font-size: 0.85rem;
    }}
    td {{
      color: var(--text);
    }}
    .prob-high {{
      color: #4ade80;
      font-weight: 700;
    }}
    .prob-mid {{
      color: #facc15;
      font-weight: 600;
    }}
    .prob-low {{
      color: #f87171;
    }}
    .prob-na {{
      color: var(--muted);
      font-style: italic;
    }}
    .value-badge {{
      display: inline-block;
      background: #fbbf24;
      color: #000;
      font-size: 0.7rem;
      font-weight: 700;
      padding: 0.15rem 0.45rem;
      border-radius: 8px;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      margin-left: 0.3rem;
      vertical-align: middle;
    }}
    .today-badge {{
      background: #dc2626;
      color: white;
      padding: 0.15rem 0.5rem;
      border-radius: 6px;
      font-size: 0.75rem;
      font-weight: 700;
      margin-left: 0.5rem;
      vertical-align: middle;
    }}
    .locked-badge {{
      background: #f59e0b;
      color: #000;
      padding: 0.15rem 0.5rem;
      border-radius: 6px;
      font-size: 0.75rem;
      font-weight: 700;
      margin-left: 0.5rem;
      vertical-align: middle;
    }}
    .footer {{
      margin-top: 2rem;
      color: var(--muted);
      font-size: 0.9rem;
      text-align: center;
    }}
    a {{
      color: var(--accent);
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
  </style>
</head>
<body>
  <div class="container">
    <h1>Premier League Home‑Win Predictions</h1>
    <p class="updated">Last updated: {last_updated}</p>
    <p class="refresh-note">Predictions are refreshed approximately one hour before kick‑off.</p>
    <div class="top-actions">
      <div class="telegram-banner">
        <span style="font-weight:600;">Telegram:</span> <a href="{telegram_link}" target="_blank" rel="noopener noreferrer">Get live predictions</a>
      </div>
      <a class="back-button" href="{portfolio_url}">← Back to Portfolio</a>
    </div>
    {performance_section}
    <div class="table-wrapper">
      <table class="predictions-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Home</th>
            <th>Away</th>
            <th>P(Home Win)</th>
            <th>Best Home Odds</th>
            <th>Value</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </div>
    <div class="footer">
      <p>Generated by an automated ML pipeline. <a href="https://github.com/Shab00">View source</a></p>
    </div>
  </div>
</body>
</html>
"""

ROW_HTML = """<tr>
  <td>{date}{badges}</td>
  <td>{home}</td>
  <td>{away}</td>
  <td class="{prob_class}">{prob_display}</td>
  <td>{odds_display}</td>
  <td>{value_badge}</td>
</tr>"""


def generate_page(snapshot_path: Path, output_path: Path) -> None:
    if not snapshot_path.exists():
        print(f"Snapshot file not found: {snapshot_path}")
        sys.exit(1)

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    today_utc = now_utc.date()
    rows_data = []
    last_generated = None

    with open(snapshot_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            date_str = row.get("kickoff_time_utc", "").strip()
            home = row.get("home_team", "").strip()
            away = row.get("away_team", "").strip()
            prob_str = row.get("prob_homewin", "").strip()
            odds_str = row.get("odds_B365H", "").strip()
            generated_str = row.get("generated_at", "").strip()

            match_dt = None
            if date_str:
                try:
                    match_dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    pass

            match_date = match_dt.date() if match_dt else None
            is_today = match_date == today_utc if match_date else False
            is_locked = False
            if match_dt:
                time_to_kickoff = match_dt.replace(tzinfo=datetime.timezone.utc) - now_utc
                if datetime.timedelta(0) < time_to_kickoff <= datetime.timedelta(hours=1):
                    is_locked = True

            prob = None
            if prob_str:
                try:
                    prob = float(prob_str)
                except ValueError:
                    pass

            odds = None
            if odds_str:
                try:
                    odds = float(odds_str)
                except ValueError:
                    odds = None

            if odds is None or odds == 0:
                prob_display = "N/A"
                prob_class = "prob-na"
                odds_display = "N/A"
                value_badge = ""
            else:
                if prob is not None:
                    prob_display = f"{prob:.2%}"
                    if prob >= 0.6:
                        prob_class = "prob-high"
                    elif prob >= 0.35:
                        prob_class = "prob-mid"
                    else:
                        prob_class = "prob-low"
                else:
                    prob_display = "N/A"
                    prob_class = "prob-na"
                odds_display = f"{odds:.2f}" if odds else "N/A"

                value_badge = ""
                if prob is not None and odds and odds > 0:
                    implied_prob = 1.0 / odds
                    if prob > implied_prob:
                        value_badge = '<span class="value-badge">VALUE</span>'

            badges = ""
            if is_locked:
                badges += ' <span class="locked-badge">FINAL</span>'
            if is_today:
                badges += ' <span class="today-badge">TODAY</span>'

            rows_data.append({
                "date": date_str[:10] if date_str else "",
                "badges": badges,
                "home": home,
                "away": away,
                "prob_display": prob_display,
                "prob_class": prob_class,
                "odds_display": odds_display,
                "value_badge": value_badge,
                "match_date_obj": match_date,
            })

            if not last_generated and generated_str:
                last_generated = generated_str

    rows_data.sort(key=lambda x: x["match_date_obj"] or datetime.date.min)

    html_rows = "\n".join(
        ROW_HTML.format(
            date=r["date"],
            badges=r["badges"],
            home=r["home"],
            away=r["away"],
            prob_display=r["prob_display"],
            prob_class=r["prob_class"],
            odds_display=r["odds_display"],
            value_badge=r["value_badge"],
        )
        for r in rows_data
    )

    # ---- Performance section ----
    performance_html = build_performance_section()

    # ---- UK local time ----
    if last_generated:
        try:
            dt_utc = datetime.datetime.fromisoformat(last_generated)
            import zoneinfo
            try:
                uk_tz = zoneinfo.ZoneInfo("Europe/London")
            except Exception:
                import pytz
                uk_tz = pytz.timezone("Europe/London")
            dt_uk = dt_utc.astimezone(uk_tz)
            last_updated = dt_uk.strftime("%Y-%m-%d %H:%M %Z")
        except Exception:
            dt_utc = datetime.datetime.fromisoformat(last_generated)
            last_updated = dt_utc.strftime("%Y-%m-%d %H:%M UTC")
    else:
        mtime = datetime.datetime.fromtimestamp(snapshot_path.stat().st_mtime, tz=datetime.timezone.utc)
        try:
            import zoneinfo
            uk_tz = zoneinfo.ZoneInfo("Europe/London")
        except Exception:
            import pytz
            uk_tz = pytz.timezone("Europe/London")
        dt_uk = mtime.astimezone(uk_tz)
        last_updated = dt_uk.strftime("%Y-%m-%d %H:%M %Z")

    html = PAGE_TEMPLATE.format(
        last_updated=last_updated,
        telegram_link=TELEGRAM_CHANNEL_LINK,
        portfolio_url=PORTFOLIO_URL,
        performance_section=performance_html,
        rows=html_rows,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding='utf-8')
    print(f"Page generated: {output_path}")


def build_performance_section() -> str:
    results_file = Path("data/processed/results_merged.csv")
    if not results_file.exists():
        return """<div class="performance-tracker">
            <h2>📊 Performance Tracker</h2>
            <p style="color: var(--muted);">Season starts 21 August – tracking will begin automatically once matches are played.</p>
        </div>"""

    try:
        import pandas as pd
        df = pd.read_csv(results_file)
        # Expected columns: home_team, away_team, prob_homewin, odds_B365H, FTR, FTHG, FTAG, is_value, correct, profit
        total = len(df)
        correct = df["correct"].sum() if "correct" in df.columns else 0
        accuracy = correct / total if total > 0 else 0

        value_bets = df[df["is_value"] == True] if "is_value" in df.columns else pd.DataFrame()
        value_total = len(value_bets)
        value_correct = value_bets["correct"].sum() if "correct" in value_bets.columns else 0
        value_accuracy = value_correct / value_total if value_total > 0 else 0
        total_profit = df["profit"].sum() if "profit" in df.columns else 0.0

        return f"""<div class="performance-tracker">
            <h2>📊 Performance Tracker</h2>
            <div class="performance-summary">
                <div class="performance-stat"><strong>Overall Accuracy:</strong> {accuracy:.1%} ({correct}/{total})</div>
                <div class="performance-stat"><strong>Value Bets:</strong> {value_total} picks</div>
                <div class="performance-stat"><strong>Value Accuracy:</strong> {value_accuracy:.1%} ({value_correct}/{value_total})</div>
                <div class="performance-stat"><strong>Value Profit:</strong> {total_profit:+.2f} units</div>
            </div>
        </div>"""
    except Exception as e:
        return f"""<div class="performance-tracker">
            <h2>📊 Performance Tracker</h2>
            <p style="color: var(--muted);">Error processing results: {e}</p>
        </div>"""


if __name__ == "__main__":
    snapshot = Path(sys.argv[1]) if len(sys.argv) > 1 else SNAPSHOT_CSV
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else OUTPUT_FILE
    generate_page(snapshot, output)
