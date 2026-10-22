"""CLI.

  python -m dailynews run [--force-digest] [--force-fetch] [--dry-run]
  python -m dailynews doctor      # check keys, Telegram, Jev, and every source once
  python -m dailynews chat-id     # print chat IDs that have messaged your bot (setup helper)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys

import httpx

from dailynews.config import Settings, load_profile, load_sources
from dailynews.sources import build_sources
from dailynews.sources.base import USER_AGENT


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=30.0, follow_redirects=True)


async def cmd_run(args) -> int:
    from dailynews.pipeline import run
    if args.dry_run:
        os.environ["DAILYNEWS_DRY_RUN"] = "1"
    settings, profile = Settings.from_env(), load_profile()
    report = await run(settings, profile, build_sources(load_sources()),
                       force_digest=args.force_digest, force_fetch=args.force_fetch)
    print(json.dumps(report.__dict__, indent=2, default=str))
    delivery_ok = settings.dry_run or bool(settings.telegram_token and settings.telegram_chat_id)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        _github_report(report, settings, delivery_ok)
    # A green run that can't deliver anything is worse than a red one.
    return 0 if delivery_ok else 1


def _github_report(report, settings, delivery_ok: bool) -> None:
    """Surface the run outcome where you'll see it: the run's Summary tab and annotations."""
    errors = {k: v for k, v in report.fetched.items() if isinstance(v, str)}
    if report.digest_sent:
        digest = "sent" + (" (dry run, printed to log only)" if settings.dry_run else "")
    else:
        digest = f"not sent: {report.digest_reason}"
    line = (f"digest {digest} | breaking pushes: {report.breaking_sent} | new items: {report.new_items} | "
            f"Jev: {report.classified_jev}, heuristic: {report.classified_heuristic} | "
            f"feedback taps: {report.feedback} | source errors: {len(errors)}")
    t = report.telegram
    if t:
        src = "worker" if t.get("source") == "worker" else "telegram"
        line += (f" | {src}: {t.get('updates', t.get('taps', 0))} updates, {t.get('taps', 0)} taps, "
                 f"{t.get('recorded', 0)} recorded, {len(t.get('foreign_chats') or [])} foreign chats, "
                 f"{t.get('unknown_items', 0)} unknown items, {t.get('bad_data', 0)} bad data, ids {t.get('id_range')}")
    print(f"::notice title=dailynews::{line}")
    for n in report.notes:
        print(f"::warning title=dailynews::{n}")
    for k, v in errors.items():
        print(f"::warning title=source {k}::{v[:300]}")
    if not delivery_ok:
        print("::error title=dailynews::TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing in this workflow — nothing was delivered")
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as f:
            f.write("### dailynews\n\n" + line.replace(" | ", "  \n") + "\n")
            if report.notes or errors:
                f.write("\n**Warnings**\n\n" + "".join(f"- {n}\n" for n in report.notes)
                        + "".join(f"- `{k}`: {v[:200]}\n" for k, v in errors.items()))
            f.write("\n<details><summary>Full report</summary>\n\n```json\n"
                    + json.dumps(report.__dict__, indent=2, default=str) + "\n```\n</details>\n")


async def cmd_doctor(args) -> int:
    from dailynews.classify.jev import JevClient, JevError
    from dailynews.classify.questions import build_questions
    from dailynews.telegram import Telegram, TelegramError

    settings, profile = Settings.from_env(), load_profile()
    ok = True
    async with _client() as http:
        print("── Telegram")
        if settings.telegram_token:
            tg = Telegram(settings.telegram_token, settings.telegram_chat_id or "0", http)
            try:
                me = await tg.call("getMe")
                print(f"  bot: @{me.get('username')}")
                hook = await tg.call("getWebhookInfo")
                if hook.get("url"):
                    ok = False
                    print(f"  ✗ a webhook is set ({hook['url']}); getUpdates won't work. Run deleteWebhook.")
                if settings.telegram_chat_id and args.send_test:
                    await tg.send("✅ DailyNews doctor: delivery works.")
                    print("  test message sent")
            except TelegramError as e:
                ok = False
                print(f"  ✗ {e}")
        else:
            ok = False
            print("  ✗ TELEGRAM_BOT_TOKEN not set")
        if not settings.telegram_chat_id:
            ok = False
            print("  ✗ TELEGRAM_CHAT_ID not set (message your bot, then run `python -m dailynews chat-id`)")

        print("── Jev")
        if settings.typesafe_api_key:
            jev = JevClient(settings.typesafe_api_key, settings.jev_base_url, settings.jev_model)
            try:
                raw = await jev.ask(http, "Source: OpenAI blog\nTitle: Introducing GPT-6\nText: Today we are "
                                    "releasing GPT-6, our most capable model.", build_questions(profile))
                a = raw["answers"]
                print(f"  model={raw.get('model')} kind={a['kind']['choice']} topic={a['topic']['choice']} "
                      f"significance={a['significance']['score']:.2f} tokens={jev.input_tokens}")
            except JevError as e:
                ok = False
                print(f"  ✗ {e}")
        else:
            print("  ! TYPESAFE_API_KEY not set — heuristic fallback will be used")

        print("── Sources")
        only = set(args.only.split(",")) if getattr(args, "only", None) else None
        for src in build_sources(load_sources()):
            if only and src.key not in only:
                continue
            gha = os.environ.get("GITHUB_ACTIONS") == "true"
            try:
                items = await src.fetch(http)
                print(f"  ✓ {src.key:20s} {len(items):4d} items" + ("  ✗ EMPTY" if not items else ""))
                ok &= bool(items)
                if gha:
                    newest = max((i for i in items if i.published_at), key=lambda i: i.published_at, default=None)
                    sample = (f"newest: {newest.published_at:%Y-%m-%d} {newest.title[:80]}" if newest
                              else f"e.g. {items[0].title[:80]}" if items else "")
                    print(f"::notice title=source {src.key}::{len(items)} items. {sample}")
            except Exception as e:
                ok = False
                print(f"  ✗ {src.key:20s} {type(e).__name__}: {str(e)[:120]}")
                if gha:
                    print(f"::error title=source {src.key}::{type(e).__name__}: {str(e)[:200]}")
    return 0 if ok else 1


async def cmd_chat_id(args) -> int:
    from dailynews.telegram import Telegram
    settings = Settings.from_env()
    if not settings.telegram_token:
        print("Set TELEGRAM_BOT_TOKEN first.")
        return 1
    async with _client() as http:
        tg = Telegram(settings.telegram_token, "0", http)
        updates = await tg.call("getUpdates", timeout=0, allowed_updates=["message"])
    chats = {}
    for u in updates:
        chat = (u.get("message") or {}).get("chat")
        if chat:
            chats[chat["id"]] = chat.get("username") or chat.get("title") or chat.get("first_name")
    if not chats:
        print("No messages found. Send any message to your bot in Telegram, then re-run.")
        return 1
    for cid, name in chats.items():
        print(f"{cid}\t{name}")
    return 0


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    p = argparse.ArgumentParser(prog="dailynews")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--force-digest", action="store_true", help="send the digest now, even if already sent today")
    r.add_argument("--force-fetch", action="store_true", help="ignore per-source polling intervals")
    r.add_argument("--dry-run", action="store_true", help="print messages instead of sending; don't mark sent")
    d = sub.add_parser("doctor")
    d.add_argument("--send-test", action="store_true")
    d.add_argument("--only", help="comma-separated source keys to check")
    sub.add_parser("chat-id")
    args = p.parse_args()
    fn = {"run": cmd_run, "doctor": cmd_doctor, "chat-id": cmd_chat_id}[args.cmd]
    sys.exit(asyncio.run(fn(args)))


if __name__ == "__main__":
    main()
