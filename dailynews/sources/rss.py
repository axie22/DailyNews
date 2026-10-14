from __future__ import annotations

import feedparser
import httpx

from dailynews.sources.base import RawItem, Source
from dailynews.sources.util import extract_arxiv_id, strip_html, struct_to_dt


class RSSSource(Source):
    def __init__(self, key: str, url: str, group: str, lab: str | None = None,
                 min_interval_hours: float = 0.0):
        self.key, self.url, self.group, self.lab = key, url, group, lab
        self.min_interval_hours = min_interval_hours

    async def fetch(self, client: httpx.AsyncClient) -> list[RawItem]:
        resp = await client.get(self.url, follow_redirects=True)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        if feed.bozo and not feed.entries:
            raise ValueError(f"unparseable feed: {feed.bozo_exception}")
        items = []
        for e in feed.entries:
            url = e.get("link")
            if not url:
                continue
            items.append(RawItem(
                url=url,
                title=strip_html(e.get("title", "Untitled"), 300),
                source=self.key,
                group=self.group,
                lab=self.lab,
                content=strip_html(e.get("summary") or e.get("description") or ""),
                # Missing dates stay None; the store substitutes first_seen.
                published_at=struct_to_dt(e.get("published_parsed") or e.get("updated_parsed")),
                arxiv_id=extract_arxiv_id(url),
            ))
        return items
