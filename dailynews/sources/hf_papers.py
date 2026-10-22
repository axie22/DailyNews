from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from dailynews.sources.base import RawItem, Source
from dailynews.sources.util import parse_iso, strip_html

HF_DAILY_PAPERS_API = "https://huggingface.co/api/daily_papers"


class HFPapersSource(Source):
    """HF Daily Papers, one request per day for the last `days` days.

    The default endpoint only returns the latest page, which silently drops a day when the
    sweep runs every other day. Querying by date covers each day (and weekends) explicitly.
    """

    key = "hf_papers"

    def __init__(self, org_labs: dict[str, str] | None = None, min_interval_hours: float = 3.0, days: int = 3):
        self.org_labs = {k.lower(): v for k, v in (org_labs or {}).items()}
        self.min_interval_hours = min_interval_hours
        self.days = days

    async def _day(self, client: httpx.AsyncClient, day: str | None) -> list[dict]:
        params = {"limit": 100}
        if day:
            params["date"] = day
        resp = await client.get(HF_DAILY_PAPERS_API, params=params)
        resp.raise_for_status()
        return resp.json()

    async def fetch(self, client: httpx.AsyncClient) -> list[RawItem]:
        today = datetime.now(timezone.utc).date()
        days = [None] + [(today - timedelta(days=i)).isoformat() for i in range(self.days)]
        results = await asyncio.gather(*(self._day(client, d) for d in days), return_exceptions=True)
        if all(isinstance(r, Exception) for r in results):
            raise results[0]
        items, seen = [], set()
        for batch in results:
            if isinstance(batch, Exception):
                continue
            for entry in batch:
                paper = entry.get("paper") or {}
                aid = paper.get("id")
                if not aid or aid in seen:
                    continue
                seen.add(aid)
                org = (paper.get("organization") or entry.get("organization") or {}).get("name")
                items.append(RawItem(
                    url=f"https://arxiv.org/abs/{aid}",   # canonical: merges with the arXiv source
                    title=strip_html(paper.get("title") or entry.get("title") or "", 300),
                    source=self.key,
                    group="hf_papers",
                    content=strip_html(paper.get("summary") or entry.get("summary") or ""),
                    published_at=parse_iso(paper.get("submittedOnDailyAt") or paper.get("publishedAt")),
                    lab=self.org_labs.get((org or "").lower()),
                    arxiv_id=aid,
                    meta={"hf_upvotes": int(paper.get("upvotes") or 0), "hf_org": org,
                          "hf_url": f"https://huggingface.co/papers/{aid}",
                          "authors": [a.get("name") for a in paper.get("authors", [])][:12]},
                ))
        return items
