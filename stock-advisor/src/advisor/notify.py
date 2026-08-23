"""Alert delivery — the terminal-style push channel, via Telegram.

Setup (once):
1. Talk to @BotFather on Telegram → /newbot → copy the token.
2. Message your new bot anything, then open
   https://api.telegram.org/bot<TOKEN>/getUpdates and copy chat.id.
3. export TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...
"""
from __future__ import annotations

import os

import requests

MAX_LEN = 4000   # Telegram hard limit is 4096/message


def send_telegram(text: str) -> int:
    """Send text (chunked). Returns number of messages sent."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError(
            "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (see advisor/notify.py "
            "docstring for the 2-minute setup).")
    sent = 0
    for i in range(0, len(text), MAX_LEN):
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text[i:i + MAX_LEN]},
            timeout=30)
        resp.raise_for_status()
        sent += 1
    return sent


def notify_digest(capital: float = 1_000_000) -> int:
    """Build the daily digest and push it. Wire into the nightly cron."""
    from .digest import build_digest

    return send_telegram(build_digest(capital=capital))
