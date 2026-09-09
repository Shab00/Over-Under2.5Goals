import json
import os
from pathlib import Path

import requests

STRATEGY_JSON = Path("artifacts/strategy_latest.json")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

assert BOT_TOKEN, "TELEGRAM_BOT_TOKEN is required"
assert CHAT_ID, "TELEGRAM_CHAT_ID is required"

if not STRATEGY_JSON.exists():
    print(f"[strategy-telegram] {STRATEGY_JSON} not found - nothing to send.")
    raise SystemExit(0)

strategy = json.loads(STRATEGY_JSON.read_text(encoding="utf-8"))

message = strategy.get("telegram_message")

if not message:
    lines = ["<b>EPL AI Pundit Strategy</b>"]
    top_picks = strategy.get("top_picks", [])
    if not top_picks:
        lines.append("")
        lines.append("No standout picks this week.")
    for pick in top_picks:
        home = pick.get("home_team", "")
        away = pick.get("away_team", "")
        signal = pick.get("signal", "")
        confidence = pick.get("confidence", "")
        bet_type = pick.get("bet_type", "")
        stake = pick.get("stake_advice", "")
        lines.append(
            f"<b>{home} vs {away}</b>  |  {signal} ({confidence})  |  "
            f"{bet_type}  |  Stake: {stake}"
        )
    model_form = strategy.get("model_form")
    if model_form:
        lines.append("")
        lines.append(model_form)
    lines.append("")
    lines.append("Full analysis: shab00.github.io/football")
    message = "\n".join(lines)

send_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
resp = requests.post(send_url, data={
    "chat_id": CHAT_ID,
    "text": message,
    "parse_mode": "HTML"
})

print("[strategy-telegram] sent, status", resp.status_code)
print("Telegram response:", resp.text)
