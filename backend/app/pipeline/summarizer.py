import json
import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a concise ML research digest assistant.
Given a paper abstract or article excerpt, return a JSON object with:
- "summary": a 2-3 sentence TLDR written for a senior ML engineer
- "tags": a list of 2-5 topic tags from: [LLMs, RL, Vision, Multimodal, Efficiency,
  Alignment, Robotics, Diffusion, Audio, Theory, Infrastructure, Dataset, Benchmark, Other]

Return only valid JSON. No markdown fences. No preamble."""


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
async def summarize(client: httpx.AsyncClient, raw_content: str, title: str) -> dict:
    resp = await client.post(
        f"{settings.ollama_base_url}/api/chat",
        json={
            "model": settings.ollama_model,
            "stream": False,
            "think": False,  # disable qwen3 thinking mode so output is plain JSON
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Title: {title}\n\nContent: {raw_content[:1500]}"},
            ],
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    return _parse_json(content)


def _parse_json(content: str) -> dict:
    """Extract JSON from LLM output, handling common formatting issues."""
    import re
    # Strip <think>...</think> blocks
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    # Strip markdown code fences
    content = re.sub(r"^```(?:json)?\s*\n?", "", content)
    content = re.sub(r"\n?```\s*$", "", content)
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Try to find a JSON object in the response
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise
