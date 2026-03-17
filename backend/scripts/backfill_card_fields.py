"""Backfill why_it_matters and key_contribution for existing summarized articles.

Usage: .venv/bin/python scripts/backfill_card_fields.py
"""
import asyncio
import json
import logging
import re
import time

import httpx
from sqlalchemy import select

# Bootstrap the app so imports resolve
import sys
sys.path.insert(0, ".")

from app.config import settings
from app.database import async_session_factory
from app.models import Article

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

PROMPT = """Given this ML article title and summary, return a JSON object with exactly two fields:
- "why_it_matters": a single sentence (max 15 words) explaining why a practitioner should care.
  Focus on impact, not description. Example: "First method to match GPT-4 performance at 1/10th the cost."
- "key_contribution": the single most important takeaway in under 10 words.
  Example: "2x faster inference via speculative decoding" or "New SOTA on MMLU with 7B params"

Return only valid JSON. No markdown fences."""


def clean_output(content: str) -> str:
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    content = re.sub(r"^```(?:json)?\s*\n?", "", content)
    content = re.sub(r"\n?```\s*$", "", content)
    return content.strip()


async def backfill():
    async with async_session_factory() as session:
        result = await session.execute(
            select(Article).where(
                Article.is_summarized == True,  # noqa: E712
                Article.summary.isnot(None),
                Article.why_it_matters.is_(None),
            )
        )
        articles = result.scalars().all()

    if not articles:
        logger.info("No articles need backfill")
        return

    logger.info(f"Backfilling {len(articles)} articles")

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        success = 0
        failed = 0

        for i, article in enumerate(articles):
            try:
                user_msg = f"Title: {article.title}\nSummary: {article.summary}"
                t0 = time.monotonic()
                resp = await client.post(
                    f"{settings.ollama_base_url}/api/chat",
                    json={
                        "model": settings.ollama_model,
                        "stream": False,
                        "think": False,
                        "format": "json",
                        "options": {"num_predict": 128},
                        "messages": [
                            {"role": "system", "content": PROMPT},
                            {"role": "user", "content": user_msg},
                        ],
                    },
                    timeout=60.0,
                )
                elapsed = time.monotonic() - t0
                resp.raise_for_status()

                content = clean_output(resp.json()["message"]["content"])
                data = json.loads(content)

                why = data.get("why_it_matters", "").strip()
                key = data.get("key_contribution", "").strip()

                if why or key:
                    async with async_session_factory() as sess:
                        db_article = await sess.get(Article, article.id)
                        if why:
                            db_article.why_it_matters = why
                        if key:
                            db_article.key_contribution = key
                        await sess.commit()
                    success += 1
                    logger.info(f"[{i+1}/{len(articles)}] {elapsed:.1f}s - {article.title[:60]}")
                else:
                    failed += 1
                    logger.warning(f"[{i+1}/{len(articles)}] Empty result for: {article.title[:60]}")

            except Exception as e:
                failed += 1
                logger.warning(f"[{i+1}/{len(articles)}] Failed: {type(e).__name__}: {e}")

        logger.info(f"Backfill complete: {success} updated, {failed} failed out of {len(articles)}")


if __name__ == "__main__":
    asyncio.run(backfill())
