import logging
from datetime import datetime, timezone
import calendar

import feedparser
import httpx

from app.scrapers.base import BaseScraper, RawArticle

logger = logging.getLogger(__name__)

RSS_FEEDS = [
    {"url": "https://openai.com/blog/rss.xml", "source_tag": "openai"},
    {"url": "https://www.anthropic.com/rss.xml", "source_tag": "anthropic"},
    {"url": "https://deepmind.google/blog/rss.xml", "source_tag": "deepmind"},
    {"url": "https://ai.meta.com/blog/rss/", "source_tag": "meta-ai"},
    {"url": "https://bair.berkeley.edu/blog/feed.xml", "source_tag": "bair"},
    {"url": "https://www.reddit.com/r/MachineLearning/top/.rss?t=day", "source_tag": "reddit-ml"},
]


class RSSFeedsScraper(BaseScraper):
    def __init__(self, feeds: list[dict] | None = None):
        self.feeds = feeds or RSS_FEEDS

    async def fetch(self) -> list[RawArticle]:
        articles = []
        async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": "ml-news-bot/1.0"}) as client:
            for feed_config in self.feeds:
                try:
                    resp = await client.get(feed_config["url"])
                    resp.raise_for_status()
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries:
                        try:
                            published_at = None
                            if hasattr(entry, "published_parsed") and entry.published_parsed:
                                ts = calendar.timegm(entry.published_parsed)
                                published_at = datetime.fromtimestamp(ts, tz=timezone.utc)
                            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                                ts = calendar.timegm(entry.updated_parsed)
                                published_at = datetime.fromtimestamp(ts, tz=timezone.utc)
                            if not published_at:
                                published_at = datetime.now(tz=timezone.utc)

                            url = entry.get("link", "")
                            if not url:
                                continue

                            raw_content = entry.get("summary", entry.get("description", ""))
                            if raw_content:
                                # strip HTML tags
                                from bs4 import BeautifulSoup
                                raw_content = BeautifulSoup(raw_content, "lxml").get_text()[:2000]

                            articles.append(
                                RawArticle(
                                    url=url,
                                    title=entry.get("title", "Untitled").strip(),
                                    source="rss",
                                    published_at=published_at,
                                    raw_content=raw_content or "",
                                    authors=[],
                                    source_meta={"feed_source": feed_config["source_tag"]},
                                )
                            )
                        except Exception as e:
                            logger.warning(f"Failed to parse RSS entry from {feed_config['source_tag']}: {e}")
                except Exception as e:
                    logger.warning(f"Failed to fetch RSS feed {feed_config['url']}: {e}")

        logger.info(f"RSSFeedsScraper: fetched {len(articles)} articles")
        return articles
