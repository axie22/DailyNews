from dataclasses import replace
from datetime import timedelta

from dailynews.pipeline import run
from dailynews.store import Store
from fakeweb import sent_item_ids


async def go(settings, profile, sources, web, now, **kw):
    async with web.client() as http:
        return await run(settings, profile, sources, now=now, http=http, **kw)


async def test_full_day(settings, profile, sources, web, now):
    # 08:00 ET: first run of the day → digest goes out
    r = await go(settings, profile, sources, web, now)
    assert r.digest_sent and r.classified_jev > 0 and r.classified_heuristic == 0
    header, *items = web.tg_sent
    assert "ML digest" in header["text"] and not header["disable_notification"]
    assert items and all(m["disable_notification"] for m in items)
    ids = sent_item_ids(items)
    assert len(ids) == len(set(ids))

    titles = " ".join(m["text"] for m in items)
    # duplicate arXiv/HF paper shows once, with HF upvotes attached and the Google lab flag
    assert titles.count("Sparse Autoencoders") == 1 and "HF ▲87" in titles
    # the Qwen release appears as one message despite 3 repos, titled by its family
    qwen = [m["text"] for m in items if "Qwen" in m["text"]]
    assert len(qwen) == 1 and "Qwen/Qwen5-72B released" in qwen[0] and "+2 variants" in qwen[0]
    # low-value items are filtered out entirely (quality floor), even on a slow day
    everything = header["text"] + titles
    assert "Crop Yield" not in everything and "Customer story" not in everything
    assert "Singapore office" not in everything
    # the frontier-lab release ranks first
    assert "GPT-7" in items[0]["text"] or "Claude 5" in items[0]["text"]

    # an hour later: same day → no second digest, nothing re-classified, arXiv throttled
    web.tg_sent.clear()
    calls_before = web.jev_calls
    arxiv_hits = sum("arxiv.org" in u for u in web.requests)
    r2 = await go(settings, profile, sources, web, now + timedelta(hours=1))
    assert not r2.digest_sent and r2.digest_reason == "already sent today"
    assert web.jev_calls == calls_before
    assert sum("arxiv.org" in u for u in web.requests) == arxiv_hits
    assert web.tg_sent == []


async def test_feedback_roundtrip_and_foreign_chat_ignored(settings, profile, sources, web, now):
    await go(settings, profile, sources, web, now)
    item_id = sent_item_ids(web.tg_sent)[0]
    web.tap(1, item_id, 1)
    web.tap(2, item_id, -1, chat_id="999")   # a stranger who found your bot
    r = await go(settings, profile, sources, web, now + timedelta(hours=1))
    assert r.feedback == 1
    assert web.tg_edits[0]["reply_markup"]["inline_keyboard"][0][0]["text"] == "👍 ✓"
    s = Store(settings.db_path)
    assert s.db.execute("SELECT label FROM feedback WHERE item_id=?", (item_id,)).fetchone()[0] == 1
    assert s.kv_get("tg_offset") == "2"
    s.close()
    # offset advanced → the same taps aren't re-processed
    r3 = await go(settings, profile, sources, web, now + timedelta(hours=2))
    assert r3.feedback == 0


async def test_before_digest_hour_breaking_only(settings, profile, sources, web, now):
    early = now - timedelta(hours=3, minutes=30)   # 04:30 ET: quiet hours, before digest
    r = await go(settings, profile, sources, web, early)
    assert not r.digest_sent and r.breaking_sent == 0 and web.tg_sent == []

    afternoon = now + timedelta(hours=6)           # 14:00 ET, digest already sent at 08:00
    await go(settings, profile, sources, web, now)
    web.tg_sent.clear()
    web.openai_items.append(("Introducing GPT-7 mini", "https://openai.com/index/gpt-7-mini",
                             "Today we are releasing GPT-7 mini.", -5))
    r = await go(settings, profile, sources, web, afternoon, force_fetch=True)
    assert r.breaking_sent == 1
    assert web.tg_sent[0]["text"].startswith("⚡") and "GPT-7 mini" in web.tg_sent[0]["text"]


async def test_jev_down_falls_back_then_recovers(settings, profile, sources, web, now):
    web.jev_mode = "auth"
    r = await go(settings, profile, sources, web, now)
    assert r.digest_sent and r.classified_heuristic > 0 and r.classified_jev == 0
    assert any("auth" in n for n in r.notes)
    assert web.jev_calls <= settings.jev_concurrency + 1   # circuit breaker stopped the stampede

    web.jev_mode = "ok"
    r2 = await go(settings, profile, sources, web, now + timedelta(hours=1))
    assert r2.classified_jev > 0                             # heuristic features get replaced


async def test_no_key_uses_heuristic(settings, profile, sources, web, now):
    r = await go(replace(settings, typesafe_api_key=None), profile, sources, web, now)
    assert r.digest_sent and web.jev_calls == 0 and r.classified_heuristic > 0


async def test_question_change_reclassifies_rated_items(settings, profile, sources, web, now):
    await go(settings, profile, sources, web, now)
    item_id = sent_item_ids(web.tg_sent)[0]
    web.tap(1, item_id, 1)
    await go(settings, profile, sources, web, now + timedelta(hours=1))
    # Two days later the item is outside the candidate window; reword a question
    profile.raw["topics"]["other"]["description"] = "Anything else"
    calls = web.jev_calls
    await go(settings, profile, sources, web, now + timedelta(days=2))
    assert web.jev_calls > calls
    s = Store(settings.db_path)
    from dailynews.classify import current_qset
    assert s.item(item_id)["qset"] == current_qset(profile)
    s.close()


async def test_dry_run_sends_nothing_and_marks_nothing(settings, profile, sources, web, now, capsys):
    await go(replace(settings, dry_run=True, telegram_token=None), profile, sources, web, now)
    assert web.tg_sent == [] and "ML digest" in capsys.readouterr().out
    s = Store(settings.db_path)
    assert s.kv_get("last_digest_date") is None
    assert s.db.execute("SELECT count(*) FROM items WHERE status='sent'").fetchone()[0] == 0
    s.close()


async def test_broken_source_does_not_sink_run_and_is_reported(settings, profile, sources, web, now):
    web.anthropic_html = "<html></html>"
    for h in range(3):   # 04:00, 05:00, 06:00 ET — before the digest hour
        await go(settings, profile, sources, web, now - timedelta(hours=4 - h), force_fetch=True)
    r = await go(settings, profile, sources, web, now, force_fetch=True)
    assert r.digest_sent
    assert "anthropic_news" in web.tg_sent[0]["text"] and "Source issues" in web.tg_sent[0]["text"]


async def test_chat_id_secret_with_whitespace_still_matches(settings, profile, sources, web, now):
    await go(settings, profile, sources, web, now)
    item_id = sent_item_ids(web.tg_sent)[0]
    web.tap(1, item_id, -1)
    r = await go(replace(settings, telegram_chat_id=" 42\n"), profile, sources, web, now + timedelta(hours=1))
    assert r.feedback == 1 and not r.notes


async def test_taps_from_mismatched_chat_are_reported(settings, profile, sources, web, now):
    await go(settings, profile, sources, web, now)
    item_id = sent_item_ids(web.tg_sent)[0]
    web.tap(1, item_id, 1, chat_id="777")
    r = await go(settings, profile, sources, web, now + timedelta(hours=1))
    assert r.feedback == 0
    assert any("777" in n and "TELEGRAM_CHAT_ID" in n for n in r.notes)
