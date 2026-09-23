import json
import os
import re
from pathlib import Path

import requests

STRATEGY_JSON = Path("artifacts/strategy_latest.json")

# Tags Telegram's HTML parse_mode actually accepts.
_TELEGRAM_ALLOWED_TAGS = {
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "a", "code", "pre", "span", "tg-spoiler", "tg-emoji", "blockquote",
}


def sanitise_html(text: str) -> str:
    """Strip anything Telegram HTML can't parse.

    Safety net for the GPT-authored telegram_message: turn <br> into newlines
    and drop every tag not on Telegram's allow-list (e.g. <footer>, <div>).
    """
    if not text:
        return text
    # <br>, <br/>, <br /> -> newline
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)

    def _keep_or_drop(m: "re.Match") -> str:
        return m.group(0) if m.group(1).lower() in _TELEGRAM_ALLOWED_TAGS else ""

    # remove opening/closing tags whose name is not allowed, keep their text
    text = re.sub(r"</?([A-Za-z0-9-]+)(?:\s[^>]*)?>", _keep_or_drop, text)
    # tidy up whitespace left behind
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
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
    if strategy.get("mode") == "no_fixtures":
        # write_no_fixtures_strategy() never sets telegram_message - build a
        # clean one here from mode/next_matchday/lookback_ready/lookback_summary
        # instead of falling through to the top_picks-based builder below
        # (which would wrongly say "No standout picks this week").
        next_matchday = strategy.get("next_matchday") or "TBC"
        lookback_ready = strategy.get("lookback_ready", True)
        lookback_summary = (strategy.get("lookback_summary") or "").strip()

        if not lookback_ready:
            message = (
                "⚽ Results being confirmed — Pundit's review coming soon. "
                f"Next predictions: {next_matchday}"
            )
        elif lookback_summary:
            if len(lookback_summary) > 500:
                lookback_summary = lookback_summary[:497].rstrip() + "..."
            message = (
                "<b>Pundit's Gameweek Review</b>\n\n"
                f"{lookback_summary}\n\n"
                f"⚽ Next predictions: {next_matchday}\n"
                "Full analysis: shab00.github.io/football"
            )
        else:
            message = (
                "⚽ No fixtures this gameweek. Pundit's review and next "
                "predictions on the website: shab00.github.io/football"
            )
    else:
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

# Last-resort safety net: never send a garbled or empty message, no matter
# what shape strategy_latest.json turned out to be in.
if not message or not message.strip():
    message = (
        "⚽ EPL AI Pundit Strategy — see the latest analysis at "
        "shab00.github.io/football"
    )

message = sanitise_html(message)

send_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
resp = requests.post(send_url, data={
    "chat_id": CHAT_ID,
    "text": message,
    "parse_mode": "HTML"
})

print("[strategy-telegram] sent, status", resp.status_code)
print("Telegram response:", resp.text)
