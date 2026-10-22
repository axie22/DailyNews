"""Give title-only items (scraped listing pages: Anthropic, Goodfire, Thinking Machines) some text.

Without it Jev judges these posts from the title alone and rates them "not substantive",
even though they're often the best items of the day. We fetch each new post once and take
its meta description plus the opening paragraphs. Cheap: a handful of pages per run.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta

import httpx
from bs4 import BeautifulSoup

from dailynews.sources.util import strip_html
from dailynews.store import Store, iso

MAX_PER_RUN = 20
MAX_CHARS = 1500


def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    parts = []
    for sel in ('meta[name="description"]', 'meta[property="og:description"]', 'meta[name="twitter:description"]'):
        tag = soup.select_one(sel)
        if tag and tag.get("content"):
            parts.append(tag["content"].strip())
            break
    for bad in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        bad.decompose()
    body = soup.find("article") or soup.find("main") or soup.body or soup
    for p in body.find_all("p"):
        t = re.sub(r"\s+", " ", p.get_text(" ")).strip()
        if len(t) >= 60 and t not in parts:
            parts.append(t)
        if sum(map(len, parts)) >= MAX_CHARS:
            break
    return strip_html(" ".join(parts), MAX_CHARS)


async def enrich_page_items(store: Store, http: httpx.AsyncClient, now: datetime) -> int:
    rows = store.db.execute(
        """SELECT id, url FROM items WHERE content = '' AND cluster_id IS NULL AND status = 'new'
           AND first_seen >= ? AND coalesce(json_extract(meta, '$.enrich_tried'), 0) = 0
           ORDER BY first_seen DESC LIMIT ?""", (iso(now - timedelta(days=3)), MAX_PER_RUN)).fetchall()
    if not rows:
        return 0

    async def one(row):
        try:
            r = await http.get(row["url"], timeout=20.0, follow_redirects=True)
            r.raise_for_status()
            return row["id"], extract_text(r.text)
        except (httpx.HTTPError, ValueError):
            return row["id"], ""

    done = 0
    for item_id, text in await asyncio.gather(*(one(r) for r in rows)):
        # Mark tried either way so a page that never yields text isn't refetched every hour.
        store.db.execute("UPDATE items SET meta = json_set(meta, '$.enrich_tried', 1) WHERE id = ?", (item_id,))
        if text:
            store.db.execute("UPDATE items SET content = ? WHERE id = ?", (text, item_id))
            # Drop title-only features so Jev re-judges it with the text this run.
            store.db.execute("DELETE FROM features WHERE item_id = ?", (item_id,))
            done += 1
    store.db.commit()
    return done
