import asyncio
import logging
import math
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select

from app.database import async_session_factory
from app.models import Article, PipelineRun
from app.pipeline.dedup import filter_new, merge_by_arxiv_id, url_hash
from app.pipeline.status import pipeline_status
from app.pipeline.summarizer import summarize
from app.scrapers.arxiv import ArxivScraper
from app.scrapers.huggingface import HFPapersScraper
from app.scrapers.rss import RSSFeedsScraper
from app.scrapers.x_api import XApiScraper

logger = logging.getLogger(__name__)

# How many articles to summarize per round before running recommendations
ROUND_SIZE = 5


async def _ollama_pull_model(client: httpx.AsyncClient) -> bool:
    """Pull the configured model into Ollama. Returns True on success."""
    from app.config import settings
    pipeline_status.ollama_status = "pulling"
    logger.info(f"Pulling model {settings.ollama_model} into Ollama...")
    try:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/pull",
            json={"model": settings.ollama_model, "stream": False},
            timeout=600.0,  # model downloads can take a while
        )
        if resp.status_code == 200:
            logger.info(f"Model {settings.ollama_model} pulled successfully")
            return True
        else:
            logger.warning(f"Ollama pull returned {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        logger.warning(f"Ollama pull failed: {type(e).__name__}: {e}")
        return False


async def _ollama_available(client: httpx.AsyncClient, retries: int = 4) -> bool:
    """Wait for Ollama to load the model, retrying for cold starts.
    Auto-pulls the model if it returns 404 (not found)."""
    from app.config import settings
    pipeline_status.ollama_status = "waiting"
    pulled = False
    for attempt in range(retries):
        try:
            t0 = time.monotonic()
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
            elapsed = time.monotonic() - t0
            if resp.status_code == 200:
                pipeline_status.ollama_status = "ready"
                logger.info(f"Ollama ready (probe took {elapsed:.1f}s)")
                return True
            elif resp.status_code == 404 and not pulled:
                logger.warning(
                    f"Ollama returned 404 — model {settings.ollama_model} not found, attempting pull"
                )
                pulled = await _ollama_pull_model(client)
                if pulled:
                    continue  # retry probe immediately after pull
            else:
                logger.warning(f"Ollama probe returned {resp.status_code} in {elapsed:.1f}s")
        except Exception as e:
            logger.warning(f"Ollama probe failed: {type(e).__name__}: {e}")
        if attempt < retries - 1:
            wait = 10 * (attempt + 1)
            logger.info(f"Ollama not ready, retrying in {wait}s (attempt {attempt + 1}/{retries})")
            await asyncio.sleep(wait)

    pipeline_status.ollama_status = "unavailable"
    return False


async def resume_processing():
    """On startup: only summarize + recommend existing unsummarized articles.
    No scraping — avoids redundant fetches on every restart."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count())
            .select_from(Article)
            .where(Article.is_summarized == False)  # noqa: E712
        )
        unsummarized = result.scalar_one()

    if unsummarized == 0:
        logger.info("Startup: no unsummarized articles, nothing to resume")
        return

    logger.info(f"Startup: resuming processing for {unsummarized} unsummarized articles")
    pipeline_status.reset()
    pipeline_status.started_at = time.monotonic()
    await summarize_and_recommend()
    pipeline_status.phase = "idle"
    logger.info("Startup: resume complete")


async def run_pipeline():
    pipeline_status.reset()
    pipeline_status.phase = "scraping"
    pipeline_status.started_at = time.monotonic()
    logger.info("Pipeline started")

    start = time.monotonic()
    errors = []
    articles_fetched = 0
    articles_stored = 0

    # Phase 1: Scrape and store all articles
    async with async_session_factory() as session:
        all_raw = []
        for scraper in [ArxivScraper(), HFPapersScraper(), RSSFeedsScraper()]:
            try:
                t0 = time.monotonic()
                results = await scraper.fetch()
                elapsed = time.monotonic() - t0
                all_raw.extend(results)
                logger.info(
                    f"{scraper.__class__.__name__}: {len(results)} fetched in {elapsed:.1f}s"
                )
                articles_fetched += len(results)
                pipeline_status.articles_fetched = articles_fetched
            except Exception as e:
                msg = f"{scraper.__class__.__name__} failed: {e}"
                logger.error(msg)
                errors.append(msg)
                pipeline_status.add_error(msg)

        new_articles = await filter_new(session, all_raw)
        logger.info(f"Dedup (URL): {len(all_raw)} -> {len(new_articles)} new")

        new_articles = await merge_by_arxiv_id(session, new_articles)
        logger.info(f"Dedup (arXiv): -> {len(new_articles)} after cross-source merge")

        for raw in new_articles:
            from app.pipeline.arxiv_id import extract_arxiv_id
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
                    arxiv_id=raw.source_meta.get("arxiv_id") or extract_arxiv_id(raw.url),
                )
            )
            articles_stored += 1

        pipeline_status.articles_stored = articles_stored

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

    logger.info(f"Scrape complete: {articles_stored} stored in {duration_ms}ms")

    # Phase 2: Summarize + recommend interleaved
    await summarize_and_recommend()

    pipeline_status.phase = "idle"
    total_elapsed = time.monotonic() - start
    logger.info(f"Full pipeline done in {total_elapsed:.1f}s")


async def summarize_and_recommend():
    """Summarize articles one at a time, interleaving recommendation passes
    every ROUND_SIZE articles so picks appear progressively."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count())
            .select_from(Article)
            .where(Article.is_summarized == False)  # noqa: E712
        )
        total_unsummarized = result.scalar_one()

    if total_unsummarized == 0:
        logger.info("No articles to summarize, updating recommendations")
        await _update_recommendations()
        return

    pipeline_status.phase = "summarizing"
    pipeline_status.total_to_summarize = total_unsummarized
    pipeline_status.total_batches = math.ceil(total_unsummarized / ROUND_SIZE)

    logger.info(
        f"Summarize+Recommend: {total_unsummarized} articles, "
        f"~{pipeline_status.total_batches} rounds of {ROUND_SIZE}"
    )

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
        from app.config import settings as cfg
        if cfg.groq_api_key:
            pipeline_status.ollama_status = "groq"
            logger.info(f"Using Groq API ({cfg.groq_model}) for summarization")
        elif not await _ollama_available(client):
            logger.warning("Ollama unavailable, will retry next run")
            return

        total_summarized = 0
        total_failures = 0
        consecutive_failures = 0
        max_consecutive_failures = 5
        round_durations: list[float] = []

        while True:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(Article)
                    .where(Article.is_summarized == False)  # noqa: E712
                    .limit(ROUND_SIZE)
                )
                round_articles = result.scalars().all()
                if not round_articles:
                    break

                round_start = time.monotonic()
                round_summarized = 0
                round_failures = 0

                for article in round_articles:
                    try:
                        result = await summarize(
                            client, article.raw_content or "", article.title
                        )
                        article.summary = result.get("summary")
                        article.tags = result.get("tags", [])
                        score = result.get("relevance_score")
                        if isinstance(score, (int, float)) and 1 <= score <= 10:
                            article.relevance_score = int(score)
                        why = result.get("why_it_matters")
                        if isinstance(why, str) and why.strip():
                            article.why_it_matters = why.strip()
                        key = result.get("key_contribution")
                        if isinstance(key, str) and key.strip():
                            article.key_contribution = key.strip()
                        article.is_summarized = True
                        round_summarized += 1
                        consecutive_failures = 0
                    except Exception as e:
                        msg = f"Summarize failed for {article.title[:60]}: {type(e).__name__}: {e}"
                        logger.warning(msg)
                        pipeline_status.add_error(msg)
                        round_failures += 1
                        consecutive_failures += 1

                        if consecutive_failures >= max_consecutive_failures:
                            logger.error(
                                f"{max_consecutive_failures} consecutive failures, stopping"
                            )
                            pipeline_status.add_error(
                                f"Stopped: {max_consecutive_failures} consecutive failures"
                            )
                            break

                round_duration = time.monotonic() - round_start
                round_durations.append(round_duration)
                total_summarized += round_summarized
                total_failures += round_failures

                # Update status
                pipeline_status.summarized = total_summarized
                pipeline_status.summary_failures = total_failures
                pipeline_status.current_batch += 1
                pipeline_status.last_batch_duration_s = round_duration
                pipeline_status.avg_batch_duration_s = (
                    sum(round_durations) / len(round_durations)
                )

                await session.commit()

                remaining = total_unsummarized - total_summarized - total_failures
                eta = round(remaining / ROUND_SIZE * pipeline_status.avg_batch_duration_s) if ROUND_SIZE > 0 else 0

                logger.info(
                    f"Round {pipeline_status.current_batch}/{pipeline_status.total_batches}: "
                    f"{round_summarized} summarized, {round_failures} failed in {round_duration:.1f}s | "
                    f"Total: {total_summarized}/{total_unsummarized} | "
                    f"ETA: ~{eta}s"
                )

                if consecutive_failures >= max_consecutive_failures:
                    break

            # After each round, recompute top-N recommendations by score
            await _update_recommendations()
            pipeline_status.phase = "summarizing"

        # Final recommendation update
        await _update_recommendations()

    logger.info(
        f"Summarize+Recommend complete: {total_summarized} summarized, "
        f"{total_failures} failed"
    )


TOP_RECOMMENDED = 10


async def _update_recommendations():
    """Set is_recommended for the top-N articles by relevance_score.
    Pure DB operation — no LLM calls needed."""
    from datetime import timedelta

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)

    async with async_session_factory() as session:
        # Get IDs of top-N scored articles from last 7 days
        top_result = await session.execute(
            select(Article.id)
            .where(
                Article.is_summarized == True,  # noqa: E712
                Article.relevance_score.isnot(None),
                Article.published_at >= cutoff,
            )
            .order_by(Article.relevance_score.desc(), Article.published_at.desc())
            .limit(TOP_RECOMMENDED)
        )
        top_ids = {row[0] for row in top_result.all()}

        if not top_ids:
            return

        # Clear old recommendations and set new ones
        scored_result = await session.execute(
            select(Article)
            .where(
                Article.is_summarized == True,  # noqa: E712
                Article.relevance_score.isnot(None),
                Article.published_at >= cutoff,
            )
        )
        recommended_count = 0
        for article in scored_result.scalars().all():
            was_recommended = article.is_recommended
            article.is_recommended = article.id in top_ids
            if article.is_recommended:
                recommended_count += 1

        await session.commit()
        pipeline_status.recommended = recommended_count
        logger.info(f"Recommendations updated: top {recommended_count} by relevance score")


async def run_x_pipeline():
    """Fetch X/Twitter articles and store immediately without summarization."""
    logger.info("X pipeline started")
    async with async_session_factory() as session:
        scraper = XApiScraper(session)
        try:
            t0 = time.monotonic()
            results = await scraper.fetch()
            elapsed = time.monotonic() - t0
            if not results:
                logger.info(f"X pipeline: no new tweets found ({elapsed:.1f}s)")
                return
            results = [r for r in results if r.url]  # safety check
            new_articles = await filter_new(session, results)
            new_articles = await merge_by_arxiv_id(session, new_articles)
            if not new_articles:
                logger.info(f"X pipeline: all articles already exist ({elapsed:.1f}s)")
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
            logger.info(f"X pipeline: stored {len(new_articles)} articles in {elapsed:.1f}s")
        except Exception as e:
            logger.error(f"X pipeline failed: {e}")
