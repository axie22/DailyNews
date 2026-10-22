from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import feedparser
import httpx

from dailynews.sources.base import RawItem, Source
from dailynews.sources.util import extract_arxiv_id, strip_html, struct_to_dt

ARXIV_API_URL = "https://export.arxiv.org/api/query"


class ArxivSource(Source):
    """Newest submissions across the configured categories, paged.

    Digests go out every other day, so one sweep must cover ~2 days of announcements
    (~1,000–1,400 papers across cs.LG/AI/CL, stat.ML, math.OC/ST). We page newest-first
    until we pass `lookback_days` or hit `max_results`; Jev triages everything.
    """

    key = "arxiv"
    PAGE_DELAY_S = 3.0   # arXiv asks for >= 3s between API calls

    def __init__(self, query: str, max_results: int = 2000, min_interval_hours: float = 4.0,
                 page_size: int = 500, lookback_days: float = 3):
        self.query, self.max_results, self.page_size = query, max_results, page_size
        self.lookback = timedelta(days=lookback_days)
        self.min_interval_hours = min_interval_hours

    async def fetch(self, client: httpx.AsyncClient) -> list[RawItem]:
        cutoff = datetime.now(timezone.utc) - self.lookback
        items, seen = [], set()
        for start in range(0, self.max_results, self.page_size):
            if start:
                await asyncio.sleep(self.PAGE_DELAY_S)
            try:
                resp = await client.get(ARXIV_API_URL, params={
                    "search_query": self.query, "sortBy": "submittedDate", "sortOrder": "descending",
                    "start": start, "max_results": min(self.page_size, self.max_results - start),
                }, timeout=120.0)
                resp.raise_for_status()
            except httpx.HTTPError:
                if not items:
                    raise          # nothing fetched at all: report the source as failed
                break              # keep the pages we already have
            entries = feedparser.parse(resp.content).entries
            oldest = None
            for e in entries:
                aid = extract_arxiv_id(e.get("id", ""))
                if not aid or aid in seen:
                    continue
                seen.add(aid)
                published = struct_to_dt(e.get("published_parsed"))
                oldest = published if oldest is None or (published and published < oldest) else oldest
                items.append(RawItem(
                    url=f"https://arxiv.org/abs/{aid}",   # version-less: v1/v2 are one item
                    title=strip_html(e.get("title", ""), 300),
                    source=self.key,
                    group="arxiv",
                    content=strip_html(e.get("summary", "")),
                    published_at=published,
                    arxiv_id=aid,
                    meta={"authors": [a.get("name") for a in e.get("authors", [])][:12],
                          "categories": [t.get("term") for t in e.get("tags", [])][:6]},
                ))
            if len(entries) < self.page_size or (oldest and oldest < cutoff):
                break
        return items
