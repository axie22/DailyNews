from dataclasses import replace
from datetime import timedelta

from dailynews.pipeline import run
from dailynews.sources.arxiv import ArxivSource
from dailynews.sources.hf_papers import HFPapersSource
from dailynews.store import Store


async def go(settings, profile, sources, web, now, **kw):
    async with web.client() as http:
        return await run(settings, profile, sources, now=now, http=http, **kw)


def hits(web, host):
    return sum(host in u for u in web.requests)


async def test_digest_every_other_day_with_full_sweep_only_on_digest_days(settings, profile, sources, web, now):
    profile.raw["digest"]["every_days"] = 2
    r = await go(settings, profile, sources, web, now)                       # day 0, 08:00
    assert r.digest_sent and hits(web, "arxiv.org") >= 1

    web.requests.clear()
    r = await go(settings, profile, sources, web, now + timedelta(days=1))   # day 1: off day
    assert not r.digest_sent and r.digest_reason == "next digest in 1 day(s)"
    assert hits(web, "export.arxiv.org") == 0 and hits(web, "daily_papers") == 0   # full sources skipped
    assert hits(web, "openai.com") == 1                                         # lab feeds still checked

    web.requests.clear()
    r = await go(settings, profile, sources, web, now + timedelta(days=2))   # day 2: digest + full sweep
    assert r.digest_sent and hits(web, "export.arxiv.org") >= 1 and hits(web, "daily_papers") >= 1


async def test_missed_digest_day_sends_next_morning_not_a_cycle_later(settings, profile, sources, web, now):
    profile.raw["digest"]["every_days"] = 2
    await go(settings, profile, sources, web, now)
    r = await go(settings, profile, sources, web, now + timedelta(days=3))   # day 2 runs never happened
    assert r.digest_sent


async def test_header_reports_the_multi_day_span(settings, profile, sources, web, now):
    profile.raw["digest"]["every_days"] = 2
    await go(settings, profile, sources, web, now)
    web.tg_sent.clear()
    await go(settings, profile, sources, web, now + timedelta(days=2))
    assert "Jev 2d:" in web.tg_sent[0]["text"]


async def test_arxiv_pages_until_lookback_then_stops(web, monkeypatch):
    async def no_sleep(_): pass
    monkeypatch.setattr("dailynews.sources.arxiv.asyncio.sleep", no_sleep)
    monkeypatch.setattr("dailynews.sources.arxiv.datetime", type("D", (), {"now": staticmethod(lambda tz=None: web.now)}))
    # 7 papers newest-first; the 6th and 7th are older than the 3-day lookback
    web.arxiv_pages = [(f"2610.0000{i}", f"Paper {i}", "abstract", h) for i, h in enumerate([1, 5, 20, 30, 50, 80, 90])]
    src = ArxivSource("cat:cs.LG", max_results=2000, page_size=2, lookback_days=3)
    async with web.client() as http:
        items = await src.fetch(http)
    assert web.arxiv_starts == [0, 2, 4, 6][: len(web.arxiv_starts)] and web.arxiv_starts[-1] == 4
    assert len(items) == 6 and len({i.arxiv_id for i in items}) == 6


async def test_arxiv_keeps_earlier_pages_if_a_later_page_fails(web, monkeypatch):
    async def no_sleep(_): pass
    monkeypatch.setattr("dailynews.sources.arxiv.asyncio.sleep", no_sleep)
    web.arxiv_pages = [(f"2610.0000{i}", f"Paper {i}", "abstract", 1) for i in range(4)]
    orig = web.handler
    def flaky(req):
        if req.url.host == "export.arxiv.org" and int(req.url.params.get("start", 0)) > 0:
            import httpx
            return httpx.Response(503)
        return orig(req)
    web.handler = flaky
    async with web.client() as http:
        items = await ArxivSource("q", page_size=2).fetch(http)
    assert len(items) == 2


async def test_hf_papers_asks_for_each_recent_day(web):
    async with web.client() as http:
        items = await HFPapersSource({}, days=3).fetch(http)
    dated = [u for u in web.requests if "daily_papers" in u and "date=" in u]
    assert len(dated) == 3 and len(items) == 1          # same paper across days is deduped


async def test_title_only_lab_posts_get_text_before_classification(settings, profile, sources, web, now):
    await go(settings, profile, sources, web, now)
    s = Store(settings.db_path)
    row = s.db.execute("SELECT content FROM items WHERE url LIKE '%claude-5-release'").fetchone()
    s.close()
    assert "most capable model" in row["content"] and "menu" not in row["content"]
    assert any("Claude 5" in st and "most capable model" in st for st in web.jev_states)


async def test_hf_likes_refresh_on_later_fetches(settings, profile, sources, web, now):
    await go(settings, profile, sources, web, now)
    orig = web.hf_models
    web.hf_models = lambda org: [dict(m, likes=400) for m in orig(org)]
    await go(settings, profile, sources, web, now + timedelta(hours=1), force_fetch=True)
    s = Store(settings.db_path)
    likes = [s.item(r["id"])["meta"].get("likes") for r in
             s.db.execute("SELECT id FROM items WHERE source='hf_models' AND cluster_id IS NULL")]
    s.close()
    assert likes == [400]
