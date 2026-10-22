"""One entrypoint, run hourly: sync feedback → ingest → classify → breaking → digest (if due)."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

from dailynews import rank as ranking
from dailynews.classify import classify_pending
from dailynews.config import Profile, Settings
from dailynews.sources import Source
from dailynews.sources.base import USER_AGENT
from dailynews.store import Store, from_iso
from dailynews.worker_client import WorkerError, sync_from_worker
from dailynews.telegram import Telegram, TelegramError, esc, format_item, buttons, source_label

log = logging.getLogger(__name__)

JEV_PRICE_PER_M = 0.042   # USD per 1M input tokens (output is free) as of Oct 2026
BREAKING_MAX_AGE = timedelta(hours=12)


@dataclass
class RunReport:
    feedback: int = 0
    telegram: dict = field(default_factory=dict)
    fetched: dict = field(default_factory=dict)
    new_items: int = 0
    classified_jev: int = 0
    classified_heuristic: int = 0
    breaking_sent: int = 0
    digest_sent: bool = False
    digest_reason: str = ""
    notes: list[str] = field(default_factory=list)


def in_quiet_hours(local: datetime, quiet: list[int]) -> bool:
    start, end = quiet
    h = local.hour
    return (start <= h or h < end) if start > end else (start <= h < end)


async def ingest(store: Store, sources: list[Source], http: httpx.AsyncClient, now: datetime,
                 report: RunReport, force: bool = False):
    due = [s for s in sources if force or store.source_due(s.key, s.min_interval_hours, now)]

    async def one(src: Source):
        try:
            return src, await src.fetch(http), None
        except Exception as e:  # one broken source must never sink the run
            return src, [], f"{type(e).__name__}: {e}"

    for src, items, err in await asyncio.gather(*(one(s) for s in due)):
        first_run = store.last_success(src.key) is None
        new = 0 if err else store.ingest(items, now, seed=first_run)
        store.record_source_run(src.key, now, len(items), new, err)
        report.fetched[src.key] = err or len(items)
        report.new_items += new
        if err:
            log.warning("source %s failed: %s", src.key, err)


def _ranker_status(model: ranking.Model) -> str:
    if model.w is None:
        return f"prior only ({model.n}/{ranking.MIN_LABELS} ratings, need ≥{ranking.MIN_PER_CLASS} 👍 and 👎)"
    return f"learned weight {model.alpha:.0%} ({model.n} ratings)"


def _digest_header(local: datetime, picks, notable, n_new: int, health: list[str], usage: tuple[int, int],
                   model: ranking.Model) -> str:
    lines = [f"☀️ <b>ML digest · {local:%a %b %-d}</b>",
             f"{len(picks)} picks from {n_new} new items" if picks else
             f"Nothing cleared the bar today ({n_new} new items)."]
    if notable:
        lines.append("\n<b>Also notable</b>")
        for r in notable:
            lines.append(f'• <a href="{esc(r.item["url"])}">{esc(r.item["title"][:110])}</a> — '
                         f"{esc(source_label(r.item))}")
    if health:
        lines.append("\n⚠️ <b>Source issues</b>")
        lines += [f"• {esc(h)}" for h in health[:6]]
    calls, toks = usage
    lines.append(f"\n<i>Jev 24h: {calls} calls · {toks / 1000:.0f}k tokens · ~${toks / 1e6 * JEV_PRICE_PER_M:.3f}"
                 f" · ranker: {_ranker_status(model)}</i>")
    return "\n".join(lines)


async def run(settings: Settings, profile: Profile, sources: list[Source], *, now: datetime | None = None,
              force_digest: bool = False, force_fetch: bool = False,
              http: httpx.AsyncClient | None = None) -> RunReport:
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(profile.tz)
    report = RunReport()
    store = Store(settings.db_path)
    own_http = http is None
    http = http or httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=30.0, follow_redirects=True)
    try:
        tg = None
        if settings.telegram_token and settings.telegram_chat_id:
            tg = Telegram(settings.telegram_token, settings.telegram_chat_id, http, settings.dry_run)
        elif settings.dry_run:
            tg = Telegram("dry-run", "0", http, dry_run=True)
        else:
            report.notes.append("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set — nothing will be delivered")

        # 1. feedback first, so this run's ranking already reflects new taps
        worker_url = settings.worker_url
        if tg and not settings.dry_run and not worker_url:
            # Once the Worker is installed, Telegram's webhook points at <worker>/telegram and the
            # getUpdates queue is unavailable — so discover the Worker from the webhook itself.
            try:
                hook = (await tg.call("getWebhookInfo")).get("url") or ""
                if hook.endswith("/telegram"):
                    worker_url = hook[: -len("/telegram")]
                elif hook:
                    report.notes.append(f"bot webhook points somewhere unexpected ({hook}); taps can't be read")
            except TelegramError as e:
                report.notes.append(f"getWebhookInfo failed: {e}")
        if worker_url and not settings.worker_token and not settings.dry_run:
            report.notes.append("Worker is installed but STATE_KEY isn't available to the run step — taps can't be read")
        if worker_url and settings.worker_token and not settings.dry_run:
            try:
                fs = await sync_from_worker(http, worker_url, settings.worker_token, store, now)
                report.feedback, report.telegram = fs["recorded"], fs
                if fs.get("unknown_items"):
                    report.notes.append(f"{fs['unknown_items']} tap(s) referenced items no longer in the database")
            except WorkerError as e:
                report.notes.append(f"feedback sync (worker) failed: {e}")
        elif tg and not settings.dry_run and not worker_url:
            try:
                report.feedback = await tg.sync_feedback(store, now)
                fs = tg.last_sync
                report.telegram = fs
                if fs.get("foreign_chats"):
                    report.notes.append(
                        f"ignored {fs['taps'] - fs['recorded'] - fs['unknown_items']} tap(s) from chat id(s) "
                        f"{', '.join(fs['foreign_chats'])}, which don't match TELEGRAM_CHAT_ID — if that's you, "
                        f"update the secret")
                if fs.get("unknown_items"):
                    report.notes.append(f"{fs['unknown_items']} tap(s) referenced items no longer in the database")
            except TelegramError as e:
                report.notes.append(f"feedback sync failed: {e}")

        # 2. ingest + 3. classify
        await ingest(store, sources, http, now, report, force=force_fetch)
        stats = await classify_pending(store, settings, profile, now, http)
        report.classified_jev, report.classified_heuristic = stats.jev, stats.heuristic
        if stats.note:
            report.notes.append(stats.note)
        store.record_usage(now, stats.calls, stats.input_tokens)

        # 4. rank
        from dailynews.classify import current_qset
        model = ranking.train(store.labeled(current_qset(profile)), profile)
        d = profile.digest
        ranked = ranking.rank(store.candidates(now, d["window_hours"], d["max_age_days"]), profile, model)

        if not tg:
            return report

        today = local.date().isoformat()
        if not force_digest and local.hour < d["hour"]:
            digest_due, report.digest_reason = False, f"before {d['hour']}:00 local"
        elif not force_digest and store.kv_get("last_digest_date") == today:
            digest_due, report.digest_reason = False, "already sent today"
        else:
            digest_due = True

        # 5. breaking pushes (frontier-lab releases), outside quiet hours. Skipped when the
        #    digest goes out in this same run — the release will lead the digest anyway.
        b = profile.breaking
        if b.get("enabled") and not digest_due and not in_quiet_hours(local, b["quiet_hours"]):
            fresh = [r for r in ranked if now - from_iso(r.item["published_at"]) <= BREAKING_MAX_AGE]
            for r in ranking.breaking_candidates(fresh, profile):
                mid = await tg.send("⚡ <b>Breaking</b>\n" + format_item(r.item), buttons(r.item["id"]))
                if not settings.dry_run:
                    store.mark_sent(r.item["id"], "breaking", mid, r.score, now)
                report.breaking_sent += 1
            if report.breaking_sent:
                ranked = [r for r in ranked if store.item(r.item["id"])["status"] == "new"]

        # 6. morning digest, once per local day, first run at/after digest.hour
        if digest_due:
            picks, notable = ranking.select_digest(ranked, profile)
            header = _digest_header(local, picks, notable, store.count_new_since(now - timedelta(hours=24)),
                                    store.source_health(now), store.usage_since(now - timedelta(hours=24)), model)
            await tg.send(header)   # the one message that buzzes your phone
            for r in picks:
                mid = await tg.send(format_item(r.item), buttons(r.item["id"]), silent=True)
                if not settings.dry_run:
                    store.mark_sent(r.item["id"], "digest", mid, r.score, now)
            if not settings.dry_run:
                store.kv_set("last_digest_date", today)
            report.digest_sent = True

        # 7. daily housekeeping
        if store.kv_get("last_prune") != today and not settings.dry_run:
            store.prune(now)
            store.kv_set("last_prune", today)
        return report
    finally:
        store.close()
        if own_http:
            await http.aclose()
