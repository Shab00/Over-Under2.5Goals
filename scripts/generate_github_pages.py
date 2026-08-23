#!/usr/bin/env python3
import csv
import datetime
import json
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
    .model-accuracy {{
      font-size: 0.9rem;
      color: var(--muted);
      margin-top: 0.5rem;
    }}
    .legend {{
      background: rgba(17,24,39,0.7);
      border: 1px solid var(--panel-border);
      border-radius: 12px;
      padding: 1rem 1.2rem;
      margin-bottom: 1.5rem;
    }}
    .legend h3 {{
      font-size: 0.9rem;
      margin-bottom: 0.6rem;
      color: var(--accent);
    }}
    .legend-items {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 0.6rem 1.5rem;
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.85rem;
      color: var(--muted);
      white-space: nowrap;
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
      font-size: 0.9rem;
    }}
    th, td {{
      padding: 0.75rem 0.9rem;
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
      font-size: 0.8rem;
    }}
    td {{
      color: var(--text);
    }}
    .prob-cell {{
      text-align: right;
    }}
    .odds-cell {{
      text-align: right;
    }}
    .no-upcoming {{
      color: var(--muted);
      font-style: italic;
      padding: 2rem;
      text-align: center;
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
      vertical-align: middle;
    }}
    .fade-badge {{
      display: inline-block;
      background: #ef4444;
      color: #fff;
      font-size: 0.7rem;
      font-weight: 700;
      padding: 0.15rem 0.45rem;
      border-radius: 8px;
      text-transform: uppercase;
      letter-spacing: 0.03em;
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
    {legend_section}
    {performance_section}
    <div class="table-wrapper">
      <table class="predictions-table">
        <thead>
          <tr>
            <th>Kickoff (UK)</th>
            <th>Home</th>
            <th>Away</th>
            <th class="prob-cell">P(Home Win)</th>
            <th class="odds-cell">Best Home Odds</th>
            <th>Edge</th>
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
  <td class="prob-cell {prob_class}">{prob_display}</td>
  <td class="odds-cell">{odds_display}</td>
  <td>{value_badge}{fade_badge}</td>
</tr>"""


def load_fixture_times(snapshot_path: Path):
    fixtures_path = snapshot_path.parent.parent / "data" / "processed" / "updated_fixtures_with_odds.csv"
    if not fixtures_path.exists():
        return {}

    times = {}
    try:
        with open(fixtures_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                date_raw = row.get("Date", "").strip()
                home = row.get("HomeTeam", "").strip()
                away = row.get("AwayTeam", "").strip()
                if not date_raw or not home or not away:
                    continue

                try:
                    kickoff_naive = datetime.datetime.strptime(date_raw, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    kickoff_naive = datetime.datetime.strptime(date_raw[:10], "%Y-%m-%d")

                try:
                    import zoneinfo
                    uk_tz = zoneinfo.ZoneInfo("Europe/London")
                    kickoff_uk = kickoff_naive.replace(tzinfo=uk_tz)
                except Exception:
                    import pytz
                    uk_tz = pytz.timezone("Europe/London")
                    kickoff_uk = uk_tz.localize(kickoff_naive)

                kickoff_utc = kickoff_uk.astimezone(datetime.timezone.utc)
                key = f"{date_raw[:10]}|{home}|{away}"
                times[key] = kickoff_utc
    except Exception as e:
        print(f"[generate_page] Warning: could not load fixture times: {e}")

    return times


def format_kickoff(kickoff_dt):
    if not kickoff_dt:
        return ""
    try:
        import zoneinfo
        uk_tz = zoneinfo.ZoneInfo("Europe/London")
    except Exception:
        import pytz
        uk_tz = pytz.timezone("Europe/London")
    local = kickoff_dt.astimezone(uk_tz)
    return local.strftime("%a %d %b %H:%M")


def build_legend_section():
    return """<div class="legend">
      <h3>Legend</h3>
      <div class="legend-items">
        <div class="legend-item"><span class="value-badge">VALUE</span> Model sees a positive edge</div>
        <div class="legend-item"><span class="fade-badge">FADE</span> Home team likely overpriced</div>
        <div class="legend-item"><span class="today-badge">TODAY</span> Match takes place today</div>
        <div class="legend-item"><span class="locked-badge">FINAL</span> Kickoff within 1 hour</div>
        <div class="legend-item"><span style="color: var(--muted);">N/A</span> No odds available</div>
      </div>
    </div>"""


def get_model_accuracy(base_dir: Path) -> str:
    """Read latest model accuracy from metadata files relative to predictor repo root."""
    train_report = base_dir / "artifacts" / "train_report.json"
    if train_report.exists():
        try:
            data = json.loads(train_report.read_text(encoding='utf-8'))
            acc = data.get("accuracy")
            f1 = data.get("f1")
            if acc is not None:
                acc_str = f"{acc*100:.1f}%"
                if f1 is not None:
                    return f"Model training accuracy: {acc_str} · F1: {f1:.3f}"
                return f"Model training accuracy: {acc_str}"
        except Exception:
            pass

    models_dir = base_dir / "models" / "weekly" / "homewin"
    if models_dir.exists():
        metadata_files = sorted(models_dir.glob("metadata_*.json"), reverse=True)
        for mf in metadata_files:
            try:
                data = json.loads(mf.read_text(encoding='utf-8'))
                acc = data.get("accuracy")
                f1 = data.get("f1")
                if acc is not None:
                    acc_str = f"{acc*100:.1f}%"
                    if f1 is not None:
                        return f"Model training accuracy: {acc_str} · F1: {f1:.3f}"
                    return f"Model training accuracy: {acc_str}"
            except Exception:
                continue

    return "Model training accuracy: N/A"


def build_performance_section(snapshot_path: Path) -> str:
    base_dir = snapshot_path.parent.parent  # predictor repo root
    accuracy_html = get_model_accuracy(base_dir)
    accuracy_display = f'<div class="model-accuracy">{accuracy_html}</div>' if accuracy_html else ""

    results_file = base_dir / "data" / "processed" / "results_merged.csv"
    if not results_file.exists():
        return f"""<div class="performance-tracker">
            <h2>Performance Tracker</h2>
            <p style="color: var(--muted);">Season starts 21 August – tracking will begin automatically once matches are played.</p>
            {accuracy_display}
        </div>"""

    try:
        rows = []
        with open(results_file, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

        if not rows:
            return f"""<div class="performance-tracker">
                <h2>Performance Tracker</h2>
                <p style="color: var(--muted);">No results yet – check back after the first matchday.</p>
                {accuracy_display}
            </div>"""

        total = len(rows)
        correct = sum(1 for r in rows if r.get("correct", "").strip().lower() == "true")
        accuracy = correct / total if total > 0 else 0

        value_bets = [r for r in rows if r.get("is_value", "").strip().lower() == "true"]
        value_total = len(value_bets)
        value_correct = sum(1 for r in value_bets if r.get("correct", "").strip().lower() == "true")
        value_accuracy = value_correct / value_total if value_total > 0 else 0
        total_profit = sum(float(r.get("profit", 0)) for r in value_bets)

        return f"""<div class="performance-tracker">
            <h2>Performance Tracker</h2>
            <div class="performance-summary">
                <div class="performance-stat"><strong>Overall Accuracy:</strong> {accuracy:.1%} ({correct}/{total})</div>
                <div class="performance-stat"><strong>Value Bets:</strong> {value_total} picks</div>
                <div class="performance-stat"><strong>Value Accuracy:</strong> {value_accuracy:.1%} ({value_correct}/{value_total})</div>
                <div class="performance-stat"><strong>Value Profit:</strong> {total_profit:+.2f} units</div>
            </div>
            {accuracy_display}
        </div>"""
    except Exception as e:
        return f"""<div class="performance-tracker">
            <h2>Performance Tracker</h2>
            <p style="color: var(--muted);">Error processing results: {e}</p>
            {accuracy_display}
        </div>"""


def generate_page(snapshot_path: Path, output_path: Path) -> None:
    if not snapshot_path.exists():
        print(f"Snapshot file not found: {snapshot_path}")
        sys.exit(1)

    fixture_times = load_fixture_times(snapshot_path)

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

            match_key = f"{date_str[:10]}|{home}|{away}"
            kickoff_dt = fixture_times.get(match_key)

            if kickoff_dt is None and date_str:
                try:
                    kickoff_dt = datetime.datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
                except ValueError:
                    kickoff_dt = None

            if kickoff_dt is not None and kickoff_dt <= now_utc:
                continue

            if kickoff_dt is not None and kickoff_dt > now_utc + datetime.timedelta(days=7):
                continue

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
                fade_badge = ""
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
                fade_badge = ""
                if prob is not None and odds and odds > 0:
                    implied_prob = 1.0 / odds
                    diff = prob - implied_prob
                    if diff > 0:
                        value_badge = '<span class="value-badge">VALUE</span>'
                    elif diff < -0.15:
                        fade_badge = '<span class="fade-badge">FADE</span>'

            badges = ""
            if kickoff_dt is not None:
                match_date = kickoff_dt.date()
                if match_date == today_utc:
                    badges += ' <span class="today-badge">TODAY</span>'
                time_to_kickoff = kickoff_dt - now_utc
                if datetime.timedelta(0) < time_to_kickoff <= datetime.timedelta(hours=1):
                    badges += ' <span class="locked-badge">FINAL</span>'

            kickoff_display = format_kickoff(kickoff_dt) if kickoff_dt else date_str[:10]

            rows_data.append({
                "date": kickoff_display,
                "badges": badges,
                "home": home,
                "away": away,
                "prob_display": prob_display,
                "prob_class": prob_class,
                "odds_display": odds_display,
                "value_badge": value_badge,
                "fade_badge": fade_badge,
                "kickoff_dt": kickoff_dt,
            })

            if not last_generated and generated_str:
                last_generated = generated_str

    rows_data.sort(key=lambda x: x["kickoff_dt"] or datetime.datetime.max.replace(tzinfo=datetime.timezone.utc))

    if not rows_data:
        html_rows = '<tr><td colspan="6" class="no-upcoming">No upcoming fixtures – next predictions will appear closer to the next matchday.</td></tr>'
    else:
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
                fade_badge=r["fade_badge"],
            )
            for r in rows_data
        )

    performance_html = build_performance_section(snapshot_path)
    legend_html = build_legend_section()

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
        legend_section=legend_html,
        performance_section=performance_html,
        rows=html_rows,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding='utf-8')
    print(f"Page generated: {output_path}")


if __name__ == "__main__":
    snapshot = Path(sys.argv[1]) if len(sys.argv) > 1 else SNAPSHOT_CSV
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else OUTPUT_FILE
    generate_page(snapshot, output)
