import pytest
from datetime import timedelta

from dailynews.sources.base import RawItem
from dailynews.sources.hf_models import release_family
from dailynews.store import Store, normalize_url, title_key


def raw(**kw):
    base = dict(url="https://x.com/a", title="t", source="s", group="community")
    base.update(kw)
    return RawItem(**base)


def test_normalize_url_strips_tracking():
    assert normalize_url("https://www.OpenAI.com/index/gpt-7/?utm_source=x&id=3#top") == "https://openai.com/index/gpt-7?id=3"


def test_release_family_collapses_variants():
    # Sizes and quantized/variant builds of one release are one family (one digest item).
    assert release_family("Qwen/Qwen5-72B-Instruct-FP8") == release_family("Qwen/Qwen5-7B") == "qwen/qwen5"
    assert release_family("mistralai/Timestral-5M") == release_family("mistralai/Timestral-28M")
    assert release_family("nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4-LiLiCorr") == "nvidia/nvidia-nemotron-3.5-super-vl"
    assert release_family("nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-MX") == release_family("nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B")
    # ...but different models stay apart
    assert release_family("Qwen/Qwen5-72B") != release_family("Qwen/Qwen3.8-Flash-Next")


def test_training_artifacts_are_not_releases():
    from dailynews.sources.hf_models import is_junk
    for junk in ["nvidia/GR00T-N1.7-AppleToPlate-cosine40k-checkpoint-15000",
                 "nvidia/cosmos3-nano-libero10-sdg-export-S5_2_s43", "nvidia/cdf-sim2real-smt-solderlight"]:
        assert is_junk(junk), junk
    for real in ["deepseek-ai/DeepSeek-V4.1-Flash-1017", "Qwen/Qwen5-72B-Instruct", "google/gemma-4-27b-it",
                 "nvidia/Cosmos3-H-Embodied-Nano", "meta-llama/Llama-Guard-5-12B"]:
        assert not is_junk(real), real


def test_arxiv_and_hf_papers_merge_and_lab_upgrades(now):
    s = Store(":memory:")
    s.ingest([raw(url="https://arxiv.org/abs/2610.00001", title="Paper A", source="arxiv", group="arxiv",
                  arxiv_id="2610.00001", content="short", published_at=now)], now)
    s.ingest([raw(url="https://arxiv.org/abs/2610.00001v2", title="Paper A", source="hf_papers", group="hf_papers",
                  arxiv_id="2610.00001", lab="google", content="a much longer abstract", published_at=now,
                  meta={"hf_upvotes": 50, "hf_url": "https://huggingface.co/papers/2610.00001"})], now)
    rows = s.db.execute("SELECT * FROM items WHERE cluster_id IS NULL").fetchall()
    assert len(rows) == 1
    canon = s.item(rows[0]["id"])
    assert canon["lab"] == "google"                       # lab flag adopted from HF org
    assert canon["meta"]["hf_upvotes"] == 50
    assert canon["content"] == "a much longer abstract"   # keeps the richer text


def test_cross_source_headline_clusters_but_same_source_does_not(now):
    s = Store(":memory:")
    s.ingest([raw(url="https://openai.com/gpt7", title="OpenAI releases GPT-7 reasoning model today",
                  source="openai", group="lab", published_at=now)], now)
    s.ingest([raw(url="https://reddit.com/r/ml/1", title="OpenAI releases GPT-7 reasoning model today!",
                  source="reddit_ml", group="community", published_at=now)], now)
    s.ingest([raw(url="https://openai.com/gpt7-sys", title="OpenAI releases GPT-7 reasoning model today",
                  source="openai", group="lab", published_at=now)], now)
    assert s.db.execute("SELECT count(*) FROM items WHERE cluster_id IS NULL").fetchone()[0] == 2


def test_seed_only_suppresses_undated_items(now):
    s = Store(":memory:")
    n = s.ingest([raw(url="https://a.com/1", title="old undated post"),
                  raw(url="https://a.com/2", title="dated post", published_at=now - timedelta(hours=1))], now, seed=True)
    assert n == 1
    statuses = {r["url"]: r["status"] for r in s.db.execute("SELECT url, status FROM items")}
    assert statuses == {"https://a.com/1": "seed", "https://a.com/2": "new"}


def test_source_health_flags_repeated_failures(now):
    s = Store(":memory:")
    for i in range(3):
        s.record_source_run("anthropic_news", now - timedelta(hours=i), 0, error="RuntimeError: layout changed")
        s.record_source_run("openai", now - timedelta(hours=i), 10)
    warnings = s.source_health(now)
    assert len(warnings) == 1 and warnings[0].startswith("anthropic_news")


def test_title_key_ignores_stopwords_and_order():
    assert title_key("The GPT-7 Release for Developers") == title_key("developers release gpt 7")


async def test_sources_parse_fixtures(web, sources):
    async with web.client() as http:
        got = {s.key: await s.fetch(http) for s in sources}
    assert [i.title for i in got["openai"]][0] == "Introducing GPT-7"
    assert all(i.lab == "openai" for i in got["openai"])
    gf = got["goodfire_blog"]
    assert [g.title for g in gf] == ["We can and must solve alignment with interpretability",
                                     "A practical guide to sparse autoencoders (SAEs)"]
    assert [g.url for g in gf] == ["https://www.goodfire.com/blog/we-can-and-must-solve-alignment",
                                   "https://www.goodfire.com/blog/a-practical-guide-to-saes"]
    assert [(g.published_at.month, g.published_at.day) for g in gf] == [(9, 30), (9, 28)]
    assert all(g.lab == "goodfire" for g in gf)
    anth = got["anthropic_news"]
    assert [a.title for a in anth] == ["Claude 5 is here", "Anthropic opens Singapore office"]
    assert anth[0].published_at.day == 14
    assert {i.arxiv_id for i in got["arxiv"]} == {"2610.00001", "2610.00002", "2610.00003", "2610.00004"}
    assert got["arxiv"][0].url == "https://arxiv.org/abs/2610.00001"   # version stripped
    hp = got["hf_papers"][0]
    assert hp.lab == "google" and hp.meta["hf_upvotes"] == 87
    assert {i.meta["family"] for i in got["hf_models"]} == {"qwen/qwen5"}


async def test_anthropic_layout_change_raises(web, sources):
    web.anthropic_html = "<html><body><a href='/careers'>Careers</a></body></html>"
    src = next(s for s in sources if s.key == "anthropic_news")
    async with web.client() as http:
        try:
            await src.fetch(http)
        except RuntimeError as e:
            assert "layout" in str(e)
        else:
            raise AssertionError("expected a loud failure")


async def test_listing_card_never_borrows_a_neighbours_title(web, sources):
    # Empty links whose only heading-bearing ancestor is the shared grid must be skipped,
    # not given the first post's title.
    web.goodfire_html = """<html><body><div class="grid">
      <h2>Only heading on the page</h2>
      <div><a href="/blog/post-one"></a></div><div><a href="/blog/post-two"></a></div>
    </div></body></html>"""
    src = next(s for s in sources if s.key == "goodfire_blog")
    async with web.client() as http:
        with pytest.raises(RuntimeError):
            await src.fetch(http)
