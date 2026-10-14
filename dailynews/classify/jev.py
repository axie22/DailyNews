"""Minimal async client for TypeSafe's Jev (POST /v1/systemone)."""
from __future__ import annotations

import asyncio
import logging
import random

import httpx

log = logging.getLogger(__name__)

RETRYABLE = {408, 409, 425, 429, 500, 502, 503, 504, 529}


class JevError(Exception):
    pass


class JevAuthError(JevError):
    """401/403 — retrying won't help; the caller should stop calling Jev this run."""


class JevClient:
    def __init__(self, api_key: str, base_url: str = "https://api.typesafe.ai", model: str = "jev-1.13.0",
                 max_attempts: int = 5, timeout: float = 30.0):
        self.api_key, self.model = api_key, model
        self.url = base_url.rstrip("/") + "/v1/systemone"
        self.max_attempts, self.timeout = max_attempts, timeout
        self.calls = 0
        self.input_tokens = 0

    async def ask(self, client: httpx.AsyncClient, state: str, questions: dict) -> dict:
        payload = {"state": state, "model": self.model, "questions": questions}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        for attempt in range(1, self.max_attempts + 1):
            try:
                resp = await client.post(self.url, json=payload, headers=headers, timeout=self.timeout)
            except httpx.TransportError as e:
                if attempt == self.max_attempts:
                    raise JevError(f"transport error: {e}") from e
                await asyncio.sleep(self._backoff(attempt))
                continue
            if resp.status_code in (401, 403):
                raise JevAuthError(f"{resp.status_code}: {resp.text[:200]}")
            if resp.status_code in RETRYABLE and attempt < self.max_attempts:
                await asyncio.sleep(self._retry_after(resp) or self._backoff(attempt))
                continue
            if resp.status_code >= 400:
                raise JevError(f"{resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            self.calls += 1
            self.input_tokens += int((data.get("usage") or {}).get("input_tokens", 0))
            if "answers" not in data:
                raise JevError(f"malformed response: {str(data)[:200]}")
            return data
        raise JevError("exhausted retries")

    @staticmethod
    def _retry_after(resp: httpx.Response) -> float | None:
        try:
            return min(60.0, float(resp.headers.get("retry-after", "")))
        except ValueError:
            return None

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(30.0, 0.5 * 2 ** attempt) + random.random() * 0.5


def normalize_answers(raw: dict, n_levels: int) -> dict:
    """Convert Jev's response into the backend-independent feature format we store."""
    a = raw["answers"]
    sig = a["significance"]
    score = float(sig["score"])
    return {
        "kind": {"label": a["kind"]["choice"], "probs": a["kind"]["probabilities"],
                 "confidence": a["kind"].get("confidence")},
        "topic": {"label": a["topic"]["choice"], "probs": a["topic"]["probabilities"],
                  "confidence": a["topic"].get("confidence")},
        "significance": {"score": score, "norm": score / max(1, n_levels - 1),
                         "probs": sig.get("probabilities", {}), "confidence": sig.get("confidence")},
        "substantive": {"p": float(a["substantive"]["noul"])},
    }
