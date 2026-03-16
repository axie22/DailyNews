import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select

from app.database import async_session_factory
from app.models import Article, PipelineRun
from app.pipeline.dedup import filter_new, url_hash
from app.pipeline.recommender import recommend_batch, recommend_remaining
from app.pipeline.summarizer import summarize
from app.scrapers.arxiv import ArxivScraper
from app.scrapers.huggingface import HFPapersScraper
from app.scrapers.rss import RSSFeedsScraper
from app.scrapers.x_api import XApiScraper

logger = logging.getLogger(__name__)


async def _ollama_available(client: httpx.AsyncClient, retries: int = 4) -> bool:
    """Wait for Ollama to load the model, retrying for cold starts."""
    from app.config import settings
    for attempt in range(retries):
        try:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "stream": False,
                    "think": False,
                    "messages": [{"role": "user", "content": "ping"}],
                },
                timeout=90.0,
            )
            if resp.status_code == 200:
                logger.info("Ollama ready")
                return True
        except Exception:
            pass
        if attempt < retries - 1:
            wait = 10 * (attempt + 1)
            logger.info(f"Ollama not ready, retrying in {wait}s (attempt {attempt + 1}/{retries})")
            await asyncio.sleep(wait)
    return False


async def run_pipeline():
    logger.info("Pipeline started")
    start = time.monotonic()
    errors = []
    articles_fetched = 0
    articles_stored = 0

    # Phase 1: Scrape and store all articles (fast, no Ollama dependency)
    async with async_session_factory() as session:
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

    # Phase 2: Summarize + recommend interleaved
    # After each summary batch is committed, run a recommendation pass on
    # whatever has been summarized so far. This way recommendations appear
    # progressively instead of waiting for all summaries to finish.
    await summarize_and_recommend()


async def summarize_and_recommend():
    """Interleave summarization and recommendation so recommendations
    appear as soon as summaries are available."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count())
            .select_from(Article)
            .where(Article.is_summarized == False)  # noqa: E712
        )
        total_unsummarized = result.scalar_one()

    if total_unsummarized == 0:
        # No new summaries needed, but there might be summarized articles
        # that haven't been recommended yet (e.g., from a previous partial run)
        async with httpx.AsyncClient() as client:
            if await _ollama_available(client, retries=2):
                await recommend_remaining(client)
        return

    logger.info(f"Summarize+Recommend: {total_unsummarized} articles to process")

    async with httpx.AsyncClient() as client:
        if not await _ollama_available(client):
            logger.warning("Ollama unavailable, will retry next run")
            return

        summarized = 0
        failures = 0
        max_failures = 5
        batches_since_recommend = 0

        while True:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(Article)
                    .where(Article.is_summarized == False)  # noqa: E712
                    .limit(20)
                )
                batch = result.scalars().all()
                if not batch:
                    break

                consecutive_failures = 0
                for article in batch:
                    try:
                        result = await summarize(
                            client, article.raw_content or "", article.title
                        )
                        article.summary = result.get("summary")
                        article.tags = result.get("tags", [])
                        article.is_summarized = True
                        summarized += 1
                        consecutive_failures = 0
                    except Exception as e:
                        logger.warning(f"Backfill failed for {article.url}: {e}")
                        failures += 1
                        consecutive_failures += 1
                        if consecutive_failures >= max_failures:
                            logger.error(
                                f"Backfill: {max_failures} consecutive failures, stopping"
                            )
                            await session.commit()
                            break

                await session.commit()
                batches_since_recommend += 1

                if consecutive_failures >= max_failures:
                    break

            # After every summary batch, run one recommendation pass
            # so recommendations appear progressively
            await recommend_batch(client)

        # Final pass: recommend any remaining summarized articles
        await recommend_remaining(client)

    logger.info(
        f"Summarize+Recommend complete: {summarized} summarized, {failures} failed"
    )


async def run_x_pipeline():
    """Fetch X/Twitter articles and store immediately without summarization.

    Summaries are handled later by summarize_and_recommend() to avoid Ollama
    contention with the main pipeline.
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
