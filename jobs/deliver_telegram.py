import os
import pandas as pd
import requests

PREDICTIONS_CSV = os.getenv("PREDICTIONS_CSV", "snapshots/predictions_latest.csv")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

assert BOT_TOKEN, "TELEGRAM_BOT_TOKEN is required"
assert CHAT_ID, "TELEGRAM_CHAT_ID is required"

df = pd.read_csv(PREDICTIONS_CSV)

df = df[df.get("is_predicted_fixture", 1) == 1]

df = df[df["odds_B365H"].notna() & (df["odds_B365H"] > 0)]

if df.empty:
    print("[telegram-delivery] No matches with odds to deliver.")
    exit(0)

lines = ["<b>⚽ EPL Home‑Win Predictions</b>\n"]
value_count = 0

for _, row in df.iterrows():
    prob = row["prob_homewin"]
    odds = row["odds_B365H"]
    implied_prob = 1.0 / odds
    value_mark = ""

    if prob > implied_prob:
        value_mark = "  ⭐ VALUE"
        value_count += 1

    lines.append(
        f"{row['kickoff_time_utc'][:10]}: {row['home_team']} vs {row['away_team']}  "
        f"P(Home)={prob:.2%}  Odds={odds:.2f}{value_mark}"
    )

if value_count > 0:
    lines.append(f"\n💡 {value_count} value pick(s) found — matches where the model sees an edge.")

message = "\n".join(lines)

send_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
resp = requests.post(send_url, data={
    "chat_id": CHAT_ID,
    "text": message,
    "parse_mode": "HTML"
})

print("[telegram-delivery] sent to Telegram:", resp.status_code)
print("Telegram response:", resp.text)
