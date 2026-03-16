from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawArticle:
    url: str
    title: str
    source: str
    published_at: datetime
    raw_content: str
    authors: list[str] = field(default_factory=list)
    source_meta: dict = field(default_factory=dict)


class BaseScraper(ABC):
    @abstractmethod
    async def fetch(self) -> list[RawArticle]:
        """Fetch and return new raw articles."""
        ...
