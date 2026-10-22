"""Secrets shared by the pipeline and the Cloudflare Worker, derived from existing ones.

Both sides compute the same value from STATE_KEY + TELEGRAM_BOT_TOKEN, so setup needs no
extra secrets copied between GitHub and Cloudflare. Rotating either input rotates these
(redeploy the Worker afterwards).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sys

PURPOSES = ("webhook", "pull")


def derive(purpose: str, state_key: str | None = None, bot_token: str | None = None) -> str | None:
    if purpose not in PURPOSES:
        raise ValueError(purpose)
    state_key = (state_key if state_key is not None else os.environ.get("STATE_KEY", "")).strip()
    bot_token = (bot_token if bot_token is not None else os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()
    if not state_key or not bot_token:
        return None
    # Hex output: valid for Telegram's secret_token charset [A-Za-z0-9_-], <= 256 chars.
    return hmac.new(state_key.encode(), f"dailynews:{purpose}:{bot_token}".encode(), hashlib.sha256).hexdigest()


if __name__ == "__main__":   # used by the deploy workflow: python -m dailynews.derived webhook
    v = derive(sys.argv[1])
    if not v:
        sys.exit("STATE_KEY and TELEGRAM_BOT_TOKEN must both be set")
    print(v)
