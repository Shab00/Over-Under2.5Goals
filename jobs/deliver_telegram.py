import os
import pandas as pd
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

PREDICTIONS_CSV = os.getenv("PREDICTIONS_CSV", "snapshots/predictions_latest.csv")
FIXTURES_CSV = Path("data/processed/updated_fixtures_with_odds.csv")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

assert BOT_TOKEN, "TELEGRAM_BOT_TOKEN is required"
assert CHAT_ID, "TELEGRAM_CHAT_ID is required"

def load_fixture_times():
    if not FIXTURES_CSV.exists():
        return {}
    times = {}
    try:
        df = pd.read_csv(FIXTURES_CSV, low_memory=False)
        for _, row in df.iterrows():
            date_raw = str(row.get("Date", "")).strip()
            home = str(row.get("HomeTeam", "")).strip()
            away = str(row.get("AwayTeam", "")).strip()
            if not date_raw or not home or not away:
                continue
            try:
                kickoff_naive = pd.to_datetime(date_raw, errors="coerce")
                if pd.isna(kickoff_naive):
                    continue
                try:
                    import zoneinfo
                    uk_tz = zoneinfo.ZoneInfo("Europe/London")
                    kickoff_uk = kickoff_naive.tz_localize(uk_tz)
                except Exception:
                    import pytz
                    uk_tz = pytz.timezone("Europe/London")
                    kickoff_uk = uk_tz.localize(kickoff_naive.to_pydatetime())
                kickoff_utc = kickoff_uk.astimezone(timezone.utc)
            except Exception:
                kickoff_utc = kickoff_naive.tz_localize("UTC")
            key = f"{date_raw[:10]}|{home}|{away}"
            times[key] = kickoff_utc
    except Exception as e:
        print(f"[telegram-delivery] Warning: could not load fixture times: {e}")
    return times

fixture_times = load_fixture_times()

df = pd.read_csv(PREDICTIONS_CSV)
df = df[df.get("is_predicted_fixture", 1) == 1]
df = df[df["odds_B365H"].notna() & (df["odds_B365H"] > 0)]

df["kickoff_dt"] = df.apply(
    lambda row: fixture_times.get(
        f"{str(row['kickoff_time_utc'])[:10]}|{row['home_team']}|{row['away_team']}"
    ),
    axis=1
)

now_utc = datetime.now(timezone.utc)
mask_missing = df["kickoff_dt"].isna()
if mask_missing.any():
    df.loc[mask_missing, "kickoff_dt"] = pd.to_datetime(
        df.loc[mask_missing, "kickoff_time_utc"].str[:10]
    ).dt.tz_localize("UTC")

df = df[(df["kickoff_dt"] > now_utc) & (df["kickoff_dt"] <= now_utc + timedelta(days=7))]

if df.empty:
    print("[telegram-delivery] No upcoming matches with odds in the next 7 days.")
    exit(0)

lines = ["<b>EPL Home-Win Predictions</b>"]
current_date = None

for _, row in df.iterrows():
    date = str(row["kickoff_time_utc"])[:10]
    if date != current_date:
        current_date = date
        lines.append("")
        lines.append(f"<b>{date}</b>")

    prob = row["prob_homewin"]
    odds = row["odds_B365H"]
    implied = 1.0 / odds

    # Confidence circle and label
    if prob >= 0.55:
        pred_emoji = "🟢"
        pred_label = "Home"
    elif prob <= 0.45:
        pred_emoji = "🟡"
        pred_label = "Not Home"
    else:
        pred_emoji = "🔴"
        pred_label = "Avoid"

    # Edge/Fade circle (second circle)
    edge_fade_emoji = ""
    if prob > implied:
        edge_fade_emoji = " 🔵"   # EDGE
    elif prob < implied - 0.15:
        edge_fade_emoji = " ⚫"   # FADE

    # Two circles (if edge/fade) before team name
    circles = f"{pred_emoji}{edge_fade_emoji}"

    match_line = (
        f"{circles} <b>{row['home_team']} vs {row['away_team']}</b>  |  "
        f"{pred_label}  |  Home: {prob:.1%}  |  Odds: {odds:.2f}"
    )
    lines.append(match_line)

# Legend with distinct colours
lines.append("")
lines.append("🟢 Home  ·  🟡 Not Home  ·  🔴 Avoid  ·  🔵 EDGE  ·  ⚫ FADE")

message = "\n".join(lines)

send_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
resp = requests.post(send_url, data={
    "chat_id": CHAT_ID,
    "text": message,
    "parse_mode": "HTML"
})

print("[telegram-delivery] sent to Telegram:", resp.status_code)
print("Telegram response:", resp.text)
