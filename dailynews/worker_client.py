"""Collect taps stored by the Cloudflare Worker (see worker/).

When the Worker is set up, Telegram delivers taps to it via webhook, so the bot's
getUpdates queue is no longer available to us; this replaces Telegram.sync_feedback.
The Worker has already answered each tap and drawn the ✓, so all that's left is to
record the labels and acknowledge them.
"""
from __future__ import annotations

from datetime import datetime

import httpx

from dailynews.store import Store


class WorkerError(Exception):
    pass


async def sync_from_worker(http: httpx.AsyncClient, url: str, token: str, store: Store,
                           now: datetime) -> dict:
    headers = {"authorization": f"Bearer {token}"}
    try:
        resp = await http.get(f"{url}/taps", headers=headers, timeout=20.0)
    except httpx.HTTPError as e:
        raise WorkerError(f"could not reach worker: {e}") from e
    if resp.status_code != 200:
        raise WorkerError(f"GET /taps -> {resp.status_code} {resp.text[:120]}")
    taps = resp.json().get("taps", [])

    recorded, unknown, acks = 0, 0, []
    for t in taps:
        try:
            item_id, label = int(t["item_id"]), int(t["label"])
        except (KeyError, TypeError, ValueError):
            continue
        if label not in (1, -1):
            continue
        if store.set_feedback(item_id, label, now):
            recorded += 1
        else:
            unknown += 1   # item was pruned; acknowledge anyway so it doesn't sit there forever
        acks.append({"item_id": item_id, "at": t.get("at")})

    if acks:
        try:
            r = await http.post(f"{url}/taps/ack", headers=headers, json={"acks": acks}, timeout=20.0)
            if r.status_code != 200:
                raise WorkerError(f"POST /taps/ack -> {r.status_code}")
        except httpx.HTTPError as e:
            # Labels are already saved; un-acked taps are simply re-read next run (idempotent).
            raise WorkerError(f"recorded {recorded} tap(s) but ack failed: {e}") from e
    return {"source": "worker", "taps": len(taps), "recorded": recorded, "unknown_items": unknown,
            "foreign_chats": []}
