import asyncio
import logging

import feedparser
import httpx

from app.scrapers.base import BaseScraper, RawArticle

logger = logging.getLogger(__name__)

ARXIV_API_URL = "https://export.arxiv.org/api/query"
SEARCH_QUERY = "cat:cs.LG OR cat:cs.AI OR cat:cs.CL"
MAX_RESULTS = 50


class ArxivScraper(BaseScraper):
    async def fetch(self) -> list[RawArticle]:
        params = {
            "search_query": SEARCH_QUERY,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": MAX_RESULTS,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(ARXIV_API_URL, params=params)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)

        articles = []
        for entry in feed.entries:
            try:
                arxiv_id = entry.id.split("/abs/")[-1]
                authors = [a.name for a in entry.get("authors", [])]
                # published_parsed is a time.struct_time
                from datetime import timezone
                import calendar
                published_at = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    ts = calendar.timegm(entry.published_parsed)
                    from datetime import datetime
                    published_at = datetime.fromtimestamp(ts, tz=timezone.utc)
                if published_at is None:
                    continue

                raw_content = entry.get("summary", "").strip()[:2000]
                articles.append(
                    RawArticle(
                        url=entry.id,
                        title=entry.title.replace("\n", " ").strip(),
                        source="arxiv",
                        published_at=published_at,
                        raw_content=raw_content,
                        authors=authors,
                        source_meta={"arxiv_id": arxiv_id},
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to parse arXiv entry: {e}")

        logger.info(f"ArxivScraper: fetched {len(articles)} articles")
        await asyncio.sleep(3)  # respect arXiv 3s rate limit
        return articles
