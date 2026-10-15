"""Telegram delivery + feedback collection without a server.

Buttons send callback queries to the bot. There's no webhook: each hourly run calls
getUpdates and records taps. Telegram only keeps undelivered updates for ~24h, which is
why the workflow runs hourly rather than once a day.
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
from datetime import datetime

import httpx

from dailynews.store import Store

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4096

SOURCE_NAMES = {
    "openai": "OpenAI", "deepmind": "Google DeepMind", "google_research": "Google Research",
    "google_ai_blog": "Google AI", "anthropic_news": "Anthropic", "anthropic_research": "Anthropic Research",
    "alignment_forum": "Alignment Forum", "bair": "BAIR", "reddit_ml": "r/MachineLearning",
    "arxiv": "arXiv", "hf_papers": "HF Papers", "hf_models": "HF Hub",
}
LAB_NAMES = {"openai": "OpenAI", "google": "Google", "anthropic": "Anthropic", "meta": "Meta",
             "mistral": "Mistral", "deepseek": "DeepSeek", "qwen": "Qwen", "nvidia": "NVIDIA", "xai": "xAI"}
KIND_EMOJI = {"model_release": "🚀", "research_paper": "📄", "product_or_api": "🛠", "safety_policy": "🛡",
              "tooling_infra": "🧰", "discussion_opinion": "💬", "other_news": "📰"}


def esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def snippet(text: str, limit: int = 280) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out = ""
    for s in sentences:
        if len(out) + len(s) + 1 > limit:
            break
        out = f"{out} {s}".strip()
    return out or text[: limit - 1].rsplit(" ", 1)[0] + "…"


def source_label(item: dict) -> str:
    if item.get("lab"):
        return LAB_NAMES.get(item["lab"], item["lab"].title())
    return SOURCE_NAMES.get(item["source"], item["source"])


def format_item(item: dict, rank: int | None = None) -> str:
    a = item["answers"]
    kind = a["kind"]["label"]
    topic = a["topic"]["label"].replace("_", " ")
    stars = "★" * max(1, round(a["significance"]["score"]))
    head = f"{KIND_EMOJI.get(kind, '•')} <b>{esc(source_label(item))}</b> · {esc(kind.replace('_', ' '))} · {esc(topic)} · {stars}"
    if item.get("lab"):
        head = "🏛 " + head
    lines = [head, f'<a href="{esc(item["url"])}"><b>{esc(item["title"])}</b></a>']
    if s := snippet(item.get("content", "")):
        lines.append(esc(s))
    extras = []
    meta = item.get("meta", {})
    if meta.get("hf_upvotes"):
        extras.append(f'<a href="{esc(meta.get("hf_url") or "")}">HF ▲{meta["hf_upvotes"]}</a>')
    seen = set()
    for o in meta.get("also_on", [])[:4]:
        name = SOURCE_NAMES.get(o["source"], o["source"])
        if name not in seen and o["source"] != "hf_papers":
            seen.add(name)
            extras.append(f'<a href="{esc(o["url"])}">{esc(name)}</a>')
    if meta.get("variants"):
        extras.append(f"+{len(meta['variants'])} variants")
    if extras:
        lines.append("<i>Also: " + " · ".join(extras) + "</i>")
    return "\n".join(lines)[:MAX_LEN]


def buttons(item_id: int, selected: int | None = None) -> dict:
    up = "👍 ✓" if selected == 1 else "👍"
    down = "👎 ✓" if selected == -1 else "👎"
    return {"inline_keyboard": [[{"text": up, "callback_data": f"fb:{item_id}:1"},
                                 {"text": down, "callback_data": f"fb:{item_id}:-1"}]]}


class TelegramError(Exception):
    pass


class Telegram:
    def __init__(self, token: str, chat_id: str, http: httpx.AsyncClient, dry_run: bool = False):
        self.token, self.http, self.dry_run = token, http, dry_run
        # Secrets pasted with a trailing newline/space would otherwise never match update chat ids.
        self.chat_id = str(chat_id).strip()
        self.last_sync: dict = {}
        self.sent: list[dict] = []   # dry-run log

    async def call(self, method: str, **params) -> dict:
        for attempt in range(4):
            resp = await self.http.post(API.format(token=self.token, method=method), json=params, timeout=30.0)
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            if resp.status_code == 429:
                await asyncio.sleep(min(60, int((data.get("parameters") or {}).get("retry_after", 3))) + 0.5)
                continue
            if not data.get("ok"):
                raise TelegramError(f"{method}: {resp.status_code} {data.get('description', resp.text[:200])}")
            return data["result"]
        raise TelegramError(f"{method}: rate limited")

    async def send(self, text: str, reply_markup: dict | None = None, silent: bool = False) -> int | None:
        params = {"chat_id": self.chat_id, "text": text[:MAX_LEN], "parse_mode": "HTML",
                  "disable_notification": silent, "link_preview_options": {"is_disabled": True}}
        if reply_markup:
            params["reply_markup"] = reply_markup
        if self.dry_run:
            self.sent.append(params)
            print("─" * 60 + f"\n{text}\n" + (f"[buttons: {reply_markup}]" if reply_markup else ""))
            return None
        result = await self.call("sendMessage", **params)
        await asyncio.sleep(0.35)  # stay well under per-chat rate limits
        return result.get("message_id")

    async def sync_feedback(self, store: Store, now: datetime) -> int:
        """Pull button taps since the last run and record them as labels."""
        offset = int(store.kv_get("tg_offset", "0"))
        updates = await self.call("getUpdates", offset=offset + 1 if offset else 0, timeout=0,
                                  allowed_updates=["callback_query", "message"])
        recorded, seen, foreign, unknown_item = 0, 0, set(), 0
        for u in updates:
            offset = max(offset, u["update_id"])
            cq = u.get("callback_query")
            if not cq:
                continue
            chat = str(((cq.get("message") or {}).get("chat") or {}).get("id", ""))
            seen += 1
            if chat != self.chat_id:   # anyone can message a bot; only trust your chat
                foreign.add(chat)
                continue
            m = re.fullmatch(r"fb:(\d+):(-?1)", cq.get("data", ""))
            if not m:
                continue
            item_id, label = int(m.group(1)), int(m.group(2))
            if not store.set_feedback(item_id, label, now):
                unknown_item += 1
            else:
                recorded += 1
                msg = cq.get("message") or {}
                try:
                    await self.call("editMessageReplyMarkup", chat_id=self.chat_id,
                                    message_id=msg.get("message_id"), reply_markup=buttons(item_id, label))
                except TelegramError as e:
                    log.info("could not update buttons: %s", e)
            try:  # stops the client spinner; fails harmlessly if the query is too old
                await self.call("answerCallbackQuery", callback_query_id=cq["id"], text="Noted")
            except TelegramError:
                pass
        store.kv_set("tg_offset", str(offset))
        self.last_sync = {"updates": len(updates), "taps": seen, "recorded": recorded,
                          "foreign_chats": sorted(foreign), "unknown_items": unknown_item}
        return recorded
