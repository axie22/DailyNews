from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

import httpx

from dailynews.classify import heuristic
from dailynews.classify.jev import JevAuthError, JevClient, JevError, normalize_answers
from dailynews.classify.questions import build_questions, build_state, qset_id
from dailynews.config import Profile, Settings
from dailynews.store import Store

log = logging.getLogger(__name__)

__all__ = ["classify_pending", "ClassifyStats", "current_qset"]


@dataclass
class ClassifyStats:
    jev: int = 0
    heuristic: int = 0
    failed: int = 0
    calls: int = 0
    input_tokens: int = 0
    note: str | None = None


def current_qset(profile: Profile) -> str:
    return qset_id(build_questions(profile))


async def classify_pending(store: Store, settings: Settings, profile: Profile, now: datetime,
                           http: httpx.AsyncClient) -> ClassifyStats:
    questions = build_questions(profile)
    qset = qset_id(questions)
    n_levels = len(profile.significance_levels)
    d = profile.digest
    use_jev = bool(settings.typesafe_api_key)
    pending = store.needing_features(now, qset, d["window_hours"], d["max_age_days"], include_heuristic=use_jev)
    stats = ClassifyStats()
    if not pending:
        return stats

    if not use_jev:
        stats.note = "TYPESAFE_API_KEY not set — using heuristic fallback"
        for item in pending:
            store.save_features(item["id"], qset, "heuristic", heuristic.classify(item, profile), now)
            stats.heuristic += 1
        return stats

    jev = JevClient(settings.typesafe_api_key, settings.jev_base_url, settings.jev_model)
    sem = asyncio.Semaphore(settings.jev_concurrency)
    breaker = asyncio.Event()   # set on auth failure or a run of consecutive errors
    consecutive = [0]

    async def one(item: dict):
        if breaker.is_set():
            return item, None, "circuit open"
        async with sem:
            if breaker.is_set():
                return item, None, "circuit open"
            try:
                raw = await jev.ask(http, build_state(item), questions)
                consecutive[0] = 0
                return item, (raw.get("model", settings.jev_model), normalize_answers(raw, n_levels)), None
            except JevAuthError as e:
                breaker.set()
                return item, None, f"auth: {e}"
            except (JevError, KeyError, TypeError, ValueError) as e:
                consecutive[0] += 1
                if consecutive[0] >= 8:
                    breaker.set()
                return item, None, str(e)

    results = await asyncio.gather(*(one(i) for i in pending))
    errors = []
    for item, ok, err in results:
        if ok:
            model, answers = ok
            store.save_features(item["id"], qset, model, answers, now)
            stats.jev += 1
        else:
            errors.append(err)
            # Keep the digest flowing; heuristic features are replaced on the next healthy run.
            # Rated items are never given heuristic features (they'd pollute training).
            if not store.db.execute("SELECT 1 FROM feedback WHERE item_id=?", (item["id"],)).fetchone():
                if item.get("qset") != qset:
                    store.save_features(item["id"], qset, "heuristic", heuristic.classify(item, profile), now)
                stats.heuristic += 1
            stats.failed += 1
    stats.calls, stats.input_tokens = jev.calls, jev.input_tokens
    if errors:
        stats.note = f"Jev failed for {len(errors)} item(s), e.g. {errors[0][:150]}"
        log.warning(stats.note)
    return stats
