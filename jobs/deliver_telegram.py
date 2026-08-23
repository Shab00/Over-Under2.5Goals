import os
import pandas as pd
import requests
from datetime import datetime, timezone

PREDICTIONS_CSV = os.getenv("PREDICTIONS_CSV", "snapshots/predictions_latest.csv")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

assert BOT_TOKEN, "TELEGRAM_BOT_TOKEN is required"
assert CHAT_ID, "TELEGRAM_CHAT_ID is required"

df = pd.read_csv(PREDICTIONS_CSV)
df = df[df.get("is_predicted_fixture", 1) == 1]

df = df[df["odds_B365H"].notna() & (df["odds_B365H"] > 0)]

df["kickoff_dt"] = pd.to_datetime(df["kickoff_time_utc"])
now_utc = datetime.now(timezone.utc)
if df["kickoff_dt"].dt.tz is None:
    df["kickoff_dt"] = df["kickoff_dt"].dt.tz_localize("UTC")
df = df[df["kickoff_dt"] > now_utc]

if df.empty:
    print("[telegram-delivery] No upcoming matches with odds to deliver.")
    exit(0)

lines = ["<b>EPL Home-Win Predictions</b>"]
current_date = None

for _, row in df.iterrows():
    date = row["kickoff_time_utc"][:10]
    if date != current_date:
        current_date = date
        lines.append("")
        lines.append(f"<b>{date}</b>")

    prob = row["prob_homewin"]
    odds = row["odds_B365H"]
    implied = 1.0 / odds
    tag = ""

    if prob > implied:
        tag = "  [VALUE]"
    elif prob < implied - 0.15:
        tag = "  [FADE]"

    lines.append(
        f"{row['home_team']} vs {row['away_team']}  |  "
        f"Home: {prob:.1%}  |  Odds: {odds:.2f}{tag}"
    )

message = "\n".join(lines)

send_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
resp = requests.post(send_url, data={
    "chat_id": CHAT_ID,
    "text": message,
    "parse_mode": "HTML"
})

print("[telegram-delivery] sent to Telegram:", resp.status_code)
print("Telegram response:", resp.text)
