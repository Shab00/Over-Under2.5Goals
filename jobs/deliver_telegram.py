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

if df.empty:
    print("[telegram-delivery] No matches to deliver.")
    exit(0)

lines = []
for _, row in df.iterrows():
    lines.append(
        f"{row['kickoff_time_utc']}: {row['home_team']} vs {row['away_team']} "
        f"(P(Home)={row['prob_homewin']:.2f}, Odds={row.get('odds_B365H', '')})"
    )
message = "\n".join(lines)

send_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
resp = requests.post(send_url, data={"chat_id": CHAT_ID, "text": message})

print("[telegram-delivery] sent to Telegram:", resp.status_code)
print("Telegram response:", resp.text)
