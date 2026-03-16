import json
import logging
import re
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.models import Article

logger = logging.getLogger(__name__)

RECOMMEND_PROMPT = """You are an ML research curator. Given a list of recent ML articles (each with an index, title, and summary), pick the ones that are most interesting, impactful, or novel for a senior ML engineer.

Criteria for recommendation:
- Introduces a significant new method, architecture, or result
- Has practical implications (new SOTA, usable tool, important benchmark)
- Covers a trending or high-impact topic
- Comes from notable authors or institutions
- Would spark discussion in the ML community

From the articles below, return a JSON array of the INDEX numbers you recommend.
Recommend roughly 20-30% of the articles — be selective but not too strict.

Return ONLY a JSON array of integers, e.g. [0, 2, 5, 8]. No explanation."""


async def recommend_batch(client: httpx.AsyncClient) -> int:
    """Evaluate one batch of summarized-but-not-yet-recommended articles.

    Returns the number of articles evaluated (0 means nothing left to do).
    Designed to be called repeatedly, interleaved with summarization.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)

    async with async_session_factory() as session:
        result = await session.execute(
            select(Article)
            .where(
                Article.is_summarized == True,  # noqa: E712
                Article.is_recommended.is_(None),
                Article.published_at >= cutoff,
            )
            .order_by(Article.published_at.desc())
            .limit(20)
        )
        batch = result.scalars().all()
        if not batch:
            return 0

        logger.info(f"Recommender: evaluating batch of {len(batch)} articles")

        article_list = []
        for i, article in enumerate(batch):
            summary = article.summary or article.title
            article_list.append(f"[{i}] {article.title}\n    {summary}")

        prompt = "\n\n".join(article_list)

        try:
            recommended_indices = await _get_recommendations(client, prompt)

            recommended_count = 0
            for i, article in enumerate(batch):
                article.is_recommended = i in recommended_indices
                if article.is_recommended:
                    recommended_count += 1

            await session.commit()
            logger.info(f"Recommender: {recommended_count}/{len(batch)} recommended")
            return len(batch)

        except Exception as e:
            logger.warning(f"Recommender batch failed: {e}")
            for article in batch:
                article.is_recommended = False
            await session.commit()
            return len(batch)


async def recommend_remaining(client: httpx.AsyncClient):
    """Drain all pending recommendation batches. Called after summarization is done."""
    total = 0
    while True:
        evaluated = await recommend_batch(client)
        if evaluated == 0:
            break
        total += evaluated
    if total > 0:
        logger.info(f"Recommender: finished evaluating all {total} remaining articles")


async def _get_recommendations(client: httpx.AsyncClient, article_list: str) -> set[int]:
    """Ask the LLM to pick the most interesting articles from a batch."""
    resp = await client.post(
        f"{settings.ollama_base_url}/api/chat",
        json={
            "model": settings.ollama_model,
            "stream": False,
            "think": False,
            "messages": [
                {"role": "system", "content": RECOMMEND_PROMPT},
                {"role": "user", "content": article_list},
            ],
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    content = resp.json()["message"]["content"]

    # Strip thinking tags and markdown fences
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    content = re.sub(r"^```(?:json)?\s*\n?", "", content)
    content = re.sub(r"\n?```\s*$", "", content)
    content = content.strip()

    try:
        indices = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\[[\d,\s]+\]", content)
        if match:
            indices = json.loads(match.group())
        else:
            logger.warning(f"Recommender: could not parse LLM output: {content[:200]}")
            return set()

    if not isinstance(indices, list):
        return set()

    return {int(i) for i in indices if isinstance(i, (int, float))}
