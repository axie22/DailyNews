from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

import httpx

USER_AGENT = "dailynews-bot/2.0 (+https://github.com/axie22/DailyNews)"


@dataclass
class RawItem:
    url: str
    title: str
    source: str                 # source key, e.g. "openai", "arxiv", "hf_models:Qwen"
    group: str                  # lab | arxiv | hf_papers | hf_models | community
    content: str = ""           # abstract / description (already a summary — we don't generate one)
    published_at: datetime | None = None   # None = unknown; first_seen is used instead
    lab: str | None = None      # frontier-lab priority flag (deterministic, never model-guessed)
    arxiv_id: str | None = None
    meta: dict = field(default_factory=dict)


class Source(ABC):
    key: str
    min_interval_hours: float = 0.0
    # "fast": polled hourly for breaking pushes (lab blogs, HF releases).
    # "full": fetched only in the sweep right before a digest (arXiv, HF papers, community).
    tier: str = "full"

    @abstractmethod
    async def fetch(self, client: httpx.AsyncClient) -> list[RawItem]:
        ...
