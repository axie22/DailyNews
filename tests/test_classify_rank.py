import httpx
import pytest

from dailynews import rank
from dailynews.classify import heuristic
from dailynews.classify.jev import JevAuthError, JevClient, normalize_answers
from dailynews.classify.questions import build_questions, build_state, qset_id


def make_item(i, topic="other", kind="research_paper", sig=1.0, lab=None, group="arxiv", profile=None):
    topics, kinds = list(profile.topics), list(profile.kinds)
    def dist(opts, w):
        return {o: (0.9 if o == w else 0.1 / (len(opts) - 1)) for o in opts}
    return {"id": i, "title": f"item {i}", "url": f"https://x/{i}", "source": group, "source_group": group,
            "lab": lab, "meta": {}, "model": "jev-1.13.0",
            "answers": {"kind": {"label": kind, "probs": dist(kinds, kind)},
                        "topic": {"label": topic, "probs": dist(topics, topic)},
                        "significance": {"score": sig, "norm": sig / 4},
                        "substantive": {"p": 0.8}}}


def test_qset_changes_with_descriptions_not_weights(profile):
    q1 = qset_id(build_questions(profile))
    profile.raw["topics"]["other"]["weight"] = 0.9
    assert qset_id(build_questions(profile)) == q1
    profile.raw["topics"]["other"]["description"] = "changed"
    assert qset_id(build_questions(profile)) != q1


def test_state_excludes_ranking_signals():
    st = build_state({"title": "T", "content": "C" * 5000, "source": "openai", "source_group": "lab",
                      "lab": "openai", "meta": {"hf_upvotes": 99}})
    assert "99" not in st and len(st) < 1600


async def test_jev_retries_429_then_succeeds(web, profile):
    web.jev_mode = "flaky"
    jev = JevClient("k")
    async with web.client() as http:
        raw = await jev.ask(http, "Source: arXiv preprint\nTitle: alignment", build_questions(profile))
    ans = normalize_answers(raw, len(profile.significance_levels))
    assert ans["kind"]["label"] == "research_paper" and web.jev_calls == 2
    assert 0 <= ans["significance"]["norm"] <= 1


async def test_jev_auth_error_is_not_retried(web, profile):
    web.jev_mode = "auth"
    async with web.client() as http:
        with pytest.raises(JevAuthError):
            await JevClient("bad").ask(http, "x", build_questions(profile))
    assert web.jev_calls == 1


def test_heuristic_outputs_valid_distributions(profile):
    out = heuristic.classify({"title": "Introducing a new inference kernel library", "content": "",
                              "source": "openai", "source_group": "lab", "lab": "openai"}, profile)
    assert abs(sum(out["kind"]["probs"].values()) - 1) < 1e-9
    assert set(out["topic"]["probs"]) == set(profile.topics)


def test_prior_prefers_interest_and_significance(profile):
    items = [make_item(1, "other", sig=1, profile=profile),
             make_item(2, "alignment_safety", sig=3, profile=profile),
             make_item(3, "alignment_safety", sig=1, profile=profile)]
    order = [r.item["id"] for r in rank.rank(items, profile, rank.Model(rank.feature_names(profile)))]
    assert order == [2, 3, 1]


def test_learning_needs_enough_labels_then_phases_in(profile):
    few = [(make_item(i, "multimodal_vision", profile=profile), 1) for i in range(10)]
    assert rank.train(few, profile).w is None
    # You keep liking vision papers and disliking agents papers, contrary to the prior's weights
    ex = ([(make_item(i, "multimodal_vision", profile=profile), 1) for i in range(20)]
          + [(make_item(100 + i, "agents_memory", profile=profile), -1) for i in range(20)])
    m = rank.train(ex, profile)
    assert m.w is not None and 0 < m.alpha <= 1
    vision = make_item(500, "multimodal_vision", profile=profile)
    agents = make_item(501, "agents_memory", profile=profile)
    prior_only = rank.Model(rank.feature_names(profile))
    f_v, f_a = rank.featurize(vision, profile), rank.featurize(agents, profile)
    assert prior_only.score(f_a) > prior_only.score(f_v)      # prior favors agents
    assert m.score(f_v) > m.score(f_a)                         # learned from you: vision wins


def test_digest_caps(profile):
    items = [make_item(i, "alignment_safety", sig=3, profile=profile) for i in range(6)]
    items += [make_item(10 + i, "pretraining", kind="model_release", sig=2, lab="qwen", group="hf_models",
                        profile=profile) for i in range(5)]
    ranked = rank.rank(items, profile, rank.Model(rank.feature_names(profile)))
    picks, notable = rank.select_digest(ranked, profile)
    topics = [p.item["answers"]["topic"]["label"] for p in picks]
    assert topics.count("alignment_safety") <= 3
    assert sum(1 for p in picks if p.item["lab"] == "qwen") <= 3
    assert sum(1 for p in picks if p.item["source_group"] in ("arxiv", "hf_papers")) <= 4
    assert len(notable) <= profile.digest["also_notable"]
