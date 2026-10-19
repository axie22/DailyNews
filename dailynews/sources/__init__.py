from __future__ import annotations

from dailynews.sources.arxiv import ArxivSource
from dailynews.sources.base import RawItem, Source
from dailynews.sources.hf_models import HFModelsSource
from dailynews.sources.hf_papers import HFPapersSource
from dailynews.sources.listing import ListingPageSource
from dailynews.sources.rss import RSSSource

__all__ = ["RawItem", "Source", "build_sources"]


def build_sources(cfg: dict) -> list[Source]:
    sources: list[Source] = []
    for s in cfg.get("rss", []):
        sources.append(RSSSource(s["key"], s["url"], s.get("group", "community"), s.get("lab"),
                                 s.get("min_interval_hours", 0)))
    # `pages` = listing pages without a feed; `anthropic` kept for older configs.
    for s in cfg.get("pages", []) + cfg.get("anthropic", []):
        sources.append(ListingPageSource(s["key"], s["url"], s.get("group", "lab"),
                                         s.get("lab"), s.get("min_interval_hours", 0)))
    if hm := cfg.get("hf_models"):
        sources.append(HFModelsSource(hm.get("orgs", {}), hm.get("min_interval_hours", 3)))
    if hp := cfg.get("hf_papers"):
        sources.append(HFPapersSource(hp.get("org_labs", {}), hp.get("min_interval_hours", 3)))
    if ax := cfg.get("arxiv"):
        sources.append(ArxivSource(ax["query"], ax.get("max_results", 400), ax.get("min_interval_hours", 4)))
    return sources
