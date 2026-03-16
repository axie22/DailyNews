import logging
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper, RawArticle

logger = logging.getLogger(__name__)

HF_PAPERS_URL = "https://huggingface.co/papers"


class HFPapersScraper(BaseScraper):
    async def fetch(self) -> list[RawArticle]:
        async with httpx.AsyncClient(timeout=30.0, headers={"User-Agent": "ml-news-bot/1.0"}) as client:
            resp = await client.get(HF_PAPERS_URL)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        articles = []

        # HF papers page structure: each paper is in an article element
        for paper in soup.select("article"):
            try:
                title_el = paper.select_one("h3")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)

                link_el = paper.select_one("a[href*='/papers/']")
                if not link_el:
                    continue
                href = link_el.get("href", "")
                if href.startswith("/"):
                    href = f"https://huggingface.co{href}"

                # Extract arxiv ID from HF URL like /papers/2401.12345
                arxiv_id = href.split("/papers/")[-1].strip()
                arxiv_url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else href

                # Try to get upvotes
                upvote_el = paper.select_one("[class*='vote']") or paper.select_one("button")
                upvotes = 0
                if upvote_el:
                    try:
                        upvotes = int(upvote_el.get_text(strip=True))
                    except (ValueError, TypeError):
                        pass

                articles.append(
                    RawArticle(
                        url=arxiv_url,
                        title=title,
                        source="huggingface",
                        published_at=datetime.now(tz=timezone.utc),
                        raw_content=title,  # HF page doesn't show abstracts
                        authors=[],
                        source_meta={"hf_url": href, "hf_upvotes": upvotes, "arxiv_id": arxiv_id},
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to parse HF paper: {e}")

        logger.info(f"HFPapersScraper: fetched {len(articles)} papers")
        return articles
