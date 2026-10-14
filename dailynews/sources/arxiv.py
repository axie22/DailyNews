from __future__ import annotations

import feedparser
import httpx

from dailynews.sources.base import RawItem, Source
from dailynews.sources.util import extract_arxiv_id, strip_html, struct_to_dt

ARXIV_API_URL = "https://export.arxiv.org/api/query"


class ArxivSource(Source):
    """Pulls the newest few hundred cs.LG/cs.AI/cs.CL submissions in ONE request.

    v1 took the newest 50, which was an arbitrary slice of the firehose. Now we take
    roughly a day's worth and let Jev triage all of it (~$0.01/day at current pricing).
    """

    key = "arxiv"

    def __init__(self, query: str, max_results: int = 400, min_interval_hours: float = 4.0):
        self.query, self.max_results = query, max_results
        self.min_interval_hours = min_interval_hours

    async def fetch(self, client: httpx.AsyncClient) -> list[RawItem]:
        resp = await client.get(ARXIV_API_URL, params={
            "search_query": self.query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": self.max_results,
        }, timeout=90.0)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        items = []
        for e in feed.entries:
            abs_url = e.get("id", "")
            aid = extract_arxiv_id(abs_url)
            if not aid:
                continue
            # Strip version so v1/v2 map to one item.
            url = f"https://arxiv.org/abs/{aid}"
            items.append(RawItem(
                url=url,
                title=strip_html(e.get("title", ""), 300),
                source=self.key,
                group="arxiv",
                content=strip_html(e.get("summary", "")),
                published_at=struct_to_dt(e.get("published_parsed")),
                arxiv_id=aid,
                meta={
                    "authors": [a.get("name") for a in e.get("authors", [])][:12],
                    "categories": [t.get("term") for t in e.get("tags", [])][:6],
                },
            ))
        return items
