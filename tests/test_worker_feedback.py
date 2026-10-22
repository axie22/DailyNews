from dataclasses import replace
from datetime import timedelta

from dailynews.pipeline import run
from dailynews.store import Store
from fakeweb import sent_item_ids


def with_worker(settings):
    return replace(settings, worker_url="https://dailynews.test.workers.dev", worker_token="pull-token")


async def go(settings, profile, sources, web, now):
    async with web.client() as http:
        return await run(settings, profile, sources, now=now, http=http)


def labels(settings):
    s = Store(settings.db_path)
    out = dict(s.db.execute("SELECT item_id, label FROM feedback").fetchall())
    s.close()
    return out


async def test_taps_come_from_worker_and_are_acked(settings, profile, sources, web, now):
    st = with_worker(settings)
    await go(st, profile, sources, web, now)
    ids = sent_item_ids(web.tg_sent)
    web.worker_taps = [{"item_id": ids[0], "label": 1, "at": "t1"}, {"item_id": ids[1], "label": -1, "at": "t2"},
                       {"item_id": 999999, "label": 1, "at": "t3"}]          # pruned item
    web.tap(5, ids[2], 1)   # would be a getUpdates tap; must be ignored in worker mode
    r = await go(st, profile, sources, web, now + timedelta(hours=1))
    assert r.feedback == 2 and r.telegram["source"] == "worker"
    assert labels(st) == {ids[0]: 1, ids[1]: -1}
    assert web.worker_taps == [] and len(web.worker_acked) == 3           # pruned one acked too
    assert any("no longer in the database" in n for n in r.notes)
    assert not any("getUpdates" in u for u in web.requests)                 # webhook mode: never poll


async def test_worker_down_doesnt_break_the_run(settings, profile, sources, web, now):
    st = with_worker(settings)
    web.worker_mode = "down"
    r = await go(st, profile, sources, web, now)
    assert r.digest_sent
    assert any("worker" in n and "503" in n for n in r.notes)


async def test_failed_ack_keeps_labels_and_rereads_harmlessly(settings, profile, sources, web, now):
    st = with_worker(settings)
    await go(st, profile, sources, web, now)
    ids = sent_item_ids(web.tg_sent)
    web.worker_taps = [{"item_id": ids[0], "label": 1, "at": "t1"}]
    web.worker_mode = "ack_fails"
    r = await go(st, profile, sources, web, now + timedelta(hours=1))
    assert labels(st) == {ids[0]: 1} and any("ack failed" in n for n in r.notes)
    web.worker_mode = "ok"
    r = await go(st, profile, sources, web, now + timedelta(hours=2))      # same tap re-read
    assert labels(st) == {ids[0]: 1} and web.worker_taps == []


async def test_without_worker_config_falls_back_to_getupdates(settings, profile, sources, web, now):
    await go(settings, profile, sources, web, now)
    ids = sent_item_ids(web.tg_sent)
    web.tap(1, ids[0], 1)
    r = await go(settings, profile, sources, web, now + timedelta(hours=1))
    assert r.feedback == 1 and labels(settings) == {ids[0]: 1}


async def test_worker_discovered_from_webhook_with_derived_token(settings, profile, sources, web, now, monkeypatch):
    """Real setup: no worker env vars — URL comes from getWebhookInfo, token from STATE_KEY + bot token."""
    from dailynews.derived import derive
    token = derive("pull", "state-key", settings.telegram_token)
    st = replace(settings, worker_token=token)
    web.webhook_url = "https://dailynews.test.workers.dev/telegram"
    web_auth = f"Bearer {token}"
    orig = web.handler

    def handler(req):   # the fake worker expects the derived token in this test
        if req.url.host == "dailynews.test.workers.dev" and req.headers.get("authorization") == web_auth:
            req.headers["authorization"] = "Bearer pull-token"
        return orig(req)
    web.handler = handler
    await go(st, profile, sources, web, now)
    ids = sent_item_ids(web.tg_sent)
    web.worker_taps = [{"item_id": ids[0], "label": 1, "at": "t1"}]
    r = await go(st, profile, sources, web, now + timedelta(hours=1))
    assert r.feedback == 1 and labels(st) == {ids[0]: 1}
    assert not any("getUpdates" in u for u in web.requests)


async def test_webhook_installed_but_no_token_is_reported(settings, profile, sources, web, now):
    web.webhook_url = "https://dailynews.test.workers.dev/telegram"
    r = await go(replace(settings, worker_token=None), profile, sources, web, now)
    assert r.digest_sent and any("STATE_KEY" in n for n in r.notes)


def test_derived_secrets_are_stable_distinct_and_telegram_safe():
    import re
    from dailynews.derived import derive
    a, b = derive("webhook", "k", "bot"), derive("pull", "k", "bot")
    assert a == derive("webhook", " k\n", "bot ") and a != b
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,256}", a)
    assert derive("pull", "", "bot") is None
