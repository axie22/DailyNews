import json
import logging
import re
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a concise ML research digest assistant.
Given a paper abstract or article excerpt, return a JSON object with:
- "summary": a 2-3 sentence TLDR written for a senior ML engineer
- "tags": a list of 2-5 topic tags from: [LLMs, RL, Vision, Multimodal, Efficiency,
  Alignment, Robotics, Diffusion, Audio, Theory, Infrastructure, Dataset, Benchmark, Other]
- "relevance_score": an integer 1-10 rating how interesting/impactful this is for ML practitioners.
  10 = groundbreaking new method or major result. 7-9 = notable and worth reading.
  4-6 = routine or incremental. 1-3 = not very relevant to ML practitioners.
  Be strict: most articles should score 4-6. Only truly exceptional work gets 8+.

Return only valid JSON. No markdown fences. No preamble."""

BATCH_SYSTEM_PROMPT = """You are a concise ML research digest assistant.
You will receive multiple articles, each labeled with an index like [0], [1], etc.
For each article, produce an object with:
- "index": the article index number
- "summary": a 2-3 sentence TLDR written for a senior ML engineer
- "tags": a list of 2-5 topic tags from: [LLMs, RL, Vision, Multimodal, Efficiency,
  Alignment, Robotics, Diffusion, Audio, Theory, Infrastructure, Dataset, Benchmark, Other]

Return a JSON object with an "articles" key containing the array of results.
Example: {"articles": [{"index": 0, "summary": "...", "tags": ["LLMs"]}, ...]}"""


async def summarize_batch(
    client: httpx.AsyncClient,
    articles: list[tuple[str, str]],
) -> list[dict]:
    """Summarize multiple articles in a single LLM call."""
    parts = []
    for i, (title, content) in enumerate(articles):
        parts.append(f"[{i}] Title: {title}\nContent: {content[:1000]}")

    prompt = "\n\n---\n\n".join(parts)
    prompt_len = len(prompt)

    t0 = time.monotonic()
    resp = await client.post(
        f"{settings.ollama_base_url}/api/chat",
        json={
            "model": settings.ollama_model,
            "stream": False,
            "think": False,
            "format": "json",
            "options": {"num_predict": 2048},
            "messages": [
                {"role": "system", "content": BATCH_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=180.0,
    )
    elapsed = time.monotonic() - t0
    resp.raise_for_status()

    content = resp.json()["message"]["content"]
    result = _parse_batch_json(content, len(articles))

    logger.info(
        f"Batch summarize: {len(articles)} articles, "
        f"{elapsed:.1f}s, {prompt_len} chars in, "
        f"{len(content)} chars out, {len(result)} parsed"
    )
    return result


async def summarize(client: httpx.AsyncClient, raw_content: str, title: str) -> dict:
    """Summarize a single article. Kept as fallback for individual retries."""
    t0 = time.monotonic()
    resp = await client.post(
        f"{settings.ollama_base_url}/api/chat",
        json={
            "model": settings.ollama_model,
            "stream": False,
            "think": False,
            "format": "json",
            "options": {"num_predict": 512},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Title: {title}\n\nContent: {raw_content[:1500]}"},
            ],
        },
        timeout=120.0,
    )
    elapsed = time.monotonic() - t0
    resp.raise_for_status()

    content = resp.json()["message"]["content"]
    result = _parse_json(content)

    logger.info(f"Single summarize: {elapsed:.1f}s, title={title[:60]}")
    return result


def _parse_json(content: str) -> dict:
    """Extract JSON from LLM output, handling common formatting issues."""
    content = _clean_llm_output(content)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


def _parse_batch_json(content: str, expected_count: int) -> list[dict]:
    """Parse a JSON array of summaries from batched LLM output."""
    content = _clean_llm_output(content)
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if match:
            result = json.loads(match.group())
        else:
            raise

    # Handle both {"articles": [...]} and bare [...] formats
    if isinstance(result, dict):
        result = result.get("articles", result.get("results", [result]))
    if isinstance(result, list):
        return result
    raise ValueError(f"Expected JSON array, got {type(result)}")


def _clean_llm_output(content: str) -> str:
    """Strip thinking tags and markdown fences from LLM output."""
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    content = re.sub(r"^```(?:json)?\s*\n?", "", content)
    content = re.sub(r"\n?```\s*$", "", content)
    return content.strip()
