from __future__ import annotations

from dailynews.sources.arxiv import ArxivSource
from dailynews.sources.base import RawItem, Source
from dailynews.sources.hf_models import HFModelsSource
from dailynews.sources.hf_papers import HFPapersSource
from dailynews.sources.listing import ListingPageSource
from dailynews.sources.rss import RSSSource

__all__ = ["RawItem", "Source", "build_sources"]


def _tier(spec: dict, default: str) -> str:
    return spec.get("tier") or default


def build_sources(cfg: dict) -> list[Source]:
    sources: list[Source] = []
    for s in cfg.get("rss", []):
        src = RSSSource(s["key"], s["url"], s.get("group", "community"), s.get("lab"),
                        s.get("min_interval_hours", 0))
        src.tier = _tier(s, "fast" if s.get("group") == "lab" else "full")
        sources.append(src)
    # `pages` = listing pages without a feed; `anthropic` kept for older configs.
    for s in cfg.get("pages", []) + cfg.get("anthropic", []):
        src = ListingPageSource(s["key"], s["url"], s.get("group", "lab"), s.get("lab"),
                                s.get("min_interval_hours", 0))
        src.tier = _tier(s, "fast")
        sources.append(src)
    if hm := cfg.get("hf_models"):
        src = HFModelsSource(hm.get("orgs", {}), hm.get("min_interval_hours", 3), hm.get("per_org", 25),
                             hm.get("min_likes", {}))
        src.tier = _tier(hm, "fast")
        sources.append(src)
    if hp := cfg.get("hf_papers"):
        sources.append(HFPapersSource(hp.get("org_labs", {}), hp.get("min_interval_hours", 3), hp.get("days", 3)))
    if ax := cfg.get("arxiv"):
        sources.append(ArxivSource(ax["query"], ax.get("max_results", 2000), ax.get("min_interval_hours", 4),
                                   ax.get("page_size", 500), ax.get("lookback_days", 3)))
    return sources
