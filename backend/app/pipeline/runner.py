import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx

from app.database import async_session_factory
from app.models import Article, PipelineRun
from app.pipeline.dedup import filter_new, url_hash
from app.pipeline.summarizer import summarize
from app.scrapers.arxiv import ArxivScraper
from app.scrapers.huggingface import HFPapersScraper
from app.scrapers.rss import RSSFeedsScraper
from app.scrapers.x_api import XApiScraper

logger = logging.getLogger(__name__)


async def _ollama_available(client: httpx.AsyncClient) -> bool:
    """Quick check: can Ollama load the model?"""
    from app.config import settings
    try:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "stream": False,
                "think": False,
                "messages": [{"role": "user", "content": "ping"}],
            },
            timeout=30.0,
        )
        return resp.status_code == 200
    except Exception:
        return False


async def run_pipeline():
    logger.info("Pipeline started")
    start = time.monotonic()
    errors = []
    articles_fetched = 0
    articles_stored = 0

    async with async_session_factory() as session:
        async with httpx.AsyncClient() as client:
            all_raw = []
            for scraper in [ArxivScraper(), HFPapersScraper(), RSSFeedsScraper()]:
                try:
                    results = await scraper.fetch()
                    all_raw.extend(results)
                    logger.info(f"{scraper.__class__.__name__}: {len(results)} fetched")
                    articles_fetched += len(results)
                except Exception as e:
                    msg = f"{scraper.__class__.__name__} failed: {e}"
                    logger.error(msg)
                    errors.append(msg)

            new_articles = await filter_new(session, all_raw)
            logger.info(f"Dedup: {len(all_raw)} -> {len(new_articles)} new")

            # Probe Ollama once before processing articles
            ollama_ok = await _ollama_available(client)
            if not ollama_ok:
                logger.warning("Ollama unavailable — storing articles without summaries")

            for raw in new_articles:
                summary = None
                tags: list[str] = []
                is_summarized = False

                if ollama_ok:
                    try:
                        result = await summarize(client, raw.raw_content, raw.title)
                        summary = result.get("summary")
                        tags = result.get("tags", [])
                        is_summarized = True
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        msg = f"Summarization failed for {raw.url}: {e}"
                        logger.error(msg)
                        errors.append(msg)

                session.add(
                    Article(
                        url=raw.url,
                        url_hash=url_hash(raw.url),
                        title=raw.title,
                        source=raw.source,
                        authors=raw.authors,
                        published_at=raw.published_at,
                        raw_content=raw.raw_content,
                        summary=summary,
                        tags=tags,
                        source_meta=raw.source_meta,
                        is_summarized=is_summarized,
                    )
                )
                articles_stored += 1

            duration_ms = int((time.monotonic() - start) * 1000)
            run = PipelineRun(
                run_at=datetime.now(tz=timezone.utc),
                duration_ms=duration_ms,
                articles_fetched=articles_fetched,
                articles_stored=articles_stored,
                errors_json={"errors": errors} if errors else None,
            )
            session.add(run)
            await session.commit()

    logger.info(f"Pipeline complete: {articles_stored} stored in {duration_ms}ms")

    # Backfill summaries for articles that were stored without them
    if ollama_ok:
        await backfill_summaries()


async def backfill_summaries():
    """Retry summarization for articles stored without summaries."""
    from sqlalchemy import select

    async with async_session_factory() as session:
        result = await session.execute(
            select(Article).where(Article.is_summarized == False).limit(50)  # noqa: E712
        )
        unsummarized = result.scalars().all()
        if not unsummarized:
            return

        logger.info(f"Backfill: {len(unsummarized)} unsummarized articles")
        async with httpx.AsyncClient() as client:
            for article in unsummarized:
                try:
                    result = await summarize(client, article.raw_content or "", article.title)
                    article.summary = result.get("summary")
                    article.tags = result.get("tags", [])
                    article.is_summarized = True
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.warning(f"Backfill failed for {article.url}: {e}")
                    break  # stop on first failure, retry next pipeline run

            await session.commit()
        logger.info("Backfill complete")


async def run_x_pipeline():
    """Fetch X/Twitter articles and store immediately without summarization.

    Summaries are handled later by backfill_summaries() to avoid Ollama contention
    with the main pipeline.
    """
    logger.info("X pipeline started")
    async with async_session_factory() as session:
        scraper = XApiScraper(session)
        try:
            results = await scraper.fetch()
            if not results:
                logger.info("X pipeline: no new tweets found")
                return
            new_articles = await filter_new(session, results)
            if not new_articles:
                logger.info("X pipeline: all articles already exist")
                return

            for raw in new_articles:
                session.add(
                    Article(
                        url=raw.url,
                        url_hash=url_hash(raw.url),
                        title=raw.title,
                        source=raw.source,
                        authors=raw.authors,
                        published_at=raw.published_at,
                        raw_content=raw.raw_content,
                        summary=None,
                        tags=[],
                        source_meta=raw.source_meta,
                        is_summarized=False,
                    )
                )

            await session.commit()
            logger.info(f"X pipeline: stored {len(new_articles)} articles")
        except Exception as e:
            logger.error(f"X pipeline failed: {e}")
