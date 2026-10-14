from __future__ import annotations

import httpx

from dailynews.sources.base import RawItem, Source
from dailynews.sources.util import parse_iso, strip_html

HF_DAILY_PAPERS_API = "https://huggingface.co/api/daily_papers"


class HFPapersSource(Source):
    """HF Daily Papers via the JSON API (v1 scraped HTML and got no abstracts).

    The API carries the abstract, community upvotes, and the submitting organization,
    which is a far more reliable frontier-lab signal than guessing affiliation from text.
    """

    key = "hf_papers"

    def __init__(self, org_labs: dict[str, str] | None = None, min_interval_hours: float = 3.0):
        self.org_labs = {k.lower(): v for k, v in (org_labs or {}).items()}
        self.min_interval_hours = min_interval_hours

    async def fetch(self, client: httpx.AsyncClient) -> list[RawItem]:
        resp = await client.get(HF_DAILY_PAPERS_API, params={"limit": 100})
        resp.raise_for_status()
        items = []
        for entry in resp.json():
            paper = entry.get("paper") or {}
            aid = paper.get("id")
            if not aid:
                continue
            org = (paper.get("organization") or entry.get("organization") or {}).get("name")
            items.append(RawItem(
                # Canonicalize to the arXiv URL so it merges with the arXiv source.
                url=f"https://arxiv.org/abs/{aid}",
                title=strip_html(paper.get("title") or entry.get("title") or "", 300),
                source=self.key,
                group="hf_papers",
                content=strip_html(paper.get("summary") or entry.get("summary") or ""),
                published_at=parse_iso(paper.get("submittedOnDailyAt") or paper.get("publishedAt")),
                lab=self.org_labs.get((org or "").lower()),
                arxiv_id=aid,
                meta={
                    "hf_upvotes": int(paper.get("upvotes") or 0),
                    "hf_org": org,
                    "hf_url": f"https://huggingface.co/papers/{aid}",
                    "authors": [a.get("name") for a in paper.get("authors", [])][:12],
                },
            ))
        return items
