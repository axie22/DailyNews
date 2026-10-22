"""Ranking = hand-set prior + logistic regression learned from your 👍/👎.

Jev is the featurizer, not the recommender: its calibrated probabilities become a
~25-dim feature vector, and a tiny linear model learns how *you* weight them. The
learned part phases in gradually (alpha) so a handful of taps can't swing the digest.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from dailynews.config import Profile

GROUPS = ["lab", "blog", "arxiv", "hf_papers", "hf_models", "community"]

PRIOR = {
    # Official lab posts (blogs, research pages) vs. lab-affiliated repos/papers. A single +2.0 for
    # both let NVIDIA training checkpoints outrank Interconnects and Lilian Weng.
    "lab": 2.0,
    "lab_affiliated": 0.5,
    "interest": 2.0,
    "significance": 2.5,
    "substantive": 1.0,
    "hf_upvotes": 1.0,
    "kind:model_release": 1.0,
    "kind:product_or_api": 0.4,
    "kind:safety_policy": 0.5,
    "kind:research_paper": 0.2,
    "kind:tooling_infra": 0.3,
    "kind:discussion_opinion": -0.6,
    "kind:other_news": -1.2,
    "group:community": -0.2,
    "group:blog": 1.2,       # writers you hand-picked (Interconnects, Lil'Log, Raschka, math blogs...)
    "hf_likes": 1.5,         # a flagship open-weights release earns hundreds of likes within a day
    "reddit": -0.8,          # [P] self-promo posts filled whole weekend digests
}

MIN_LABELS, MIN_PER_CLASS, FULL_TRUST_AT = 15, 5, 60


def feature_names(profile: Profile) -> list[str]:
    return (["lab", "lab_affiliated", "reddit", "interest", "significance", "substantive", "hf_upvotes", "hf_likes"]
            + [f"kind:{k}" for k in profile.kinds]
            + [f"topic:{t}" for t in profile.topics]
            + [f"group:{g}" for g in GROUPS])


def featurize(item: dict, profile: Profile) -> dict[str, float]:
    a = item["answers"]
    weights = profile.topic_weights
    topic_p = a["topic"]["probs"]
    f = {
        "lab": 1.0 if item.get("lab") and item["source_group"] == "lab" else 0.0,
        "lab_affiliated": 1.0 if item.get("lab") and item["source_group"] != "lab" else 0.0,
        "reddit": 1.0 if item["source"].startswith("reddit") else 0.0,
        # Expected interest under Jev's topic distribution — uses the full probabilities,
        # not the argmax, so an item that's 40% alignment / 40% agents scores sensibly.
        "interest": sum(weights.get(t, 0.0) * p for t, p in topic_p.items()),
        "significance": float(a["significance"]["norm"]),
        "substantive": float(a["substantive"]["p"]),
        "hf_upvotes": min(1.0, math.log1p(item["meta"].get("hf_upvotes", 0)) / math.log1p(150)),
        "hf_likes": (min(1.0, math.log1p(int(item["meta"].get("likes") or 0)) / math.log1p(300))
                     if item["source_group"] == "hf_models" else 0.0),
    }
    for k in profile.kinds:
        f[f"kind:{k}"] = float(a["kind"]["probs"].get(k, 0.0))
    for t in profile.topics:
        f[f"topic:{t}"] = float(topic_p.get(t, 0.0))
    for g in GROUPS:
        f[f"group:{g}"] = 1.0 if item["source_group"] == g else 0.0
    return f


@dataclass
class Model:
    names: list[str]
    w: np.ndarray | None = None
    b: float = 0.0
    alpha: float = 0.0
    n: int = 0

    def score(self, f: dict[str, float]) -> float:
        prior = sum(PRIOR.get(k, 0.0) * v for k, v in f.items())
        if self.w is None or self.alpha == 0:
            return prior
        x = np.array([f[k] for k in self.names])
        return prior + self.alpha * float(x @ self.w + self.b)


def train(examples: list[tuple[dict, int]], profile: Profile, l2: float = 1.0, iters: int = 800,
          lr: float = 0.5) -> Model:
    names = feature_names(profile)
    model = Model(names=names, n=len(examples))
    labels = [y for _, y in examples]
    pos, neg = labels.count(1), labels.count(-1)
    if len(examples) < MIN_LABELS or min(pos, neg) < MIN_PER_CLASS:
        return model
    X = np.array([[featurize(it, profile)[k] for k in names] for it, _ in examples])
    y = np.array([1.0 if l > 0 else 0.0 for l in labels])
    w, b = np.zeros(X.shape[1]), 0.0
    m = len(y)
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(X @ w + b)))
        g = p - y
        w -= lr * (X.T @ g / m + l2 * w / m)
        b -= lr * g.mean()
    model.w, model.b = w, b
    model.alpha = min(1.0, len(examples) / FULL_TRUST_AT)
    return model


@dataclass
class Ranked:
    item: dict
    score: float
    features: dict[str, float]


def rank(items: list[dict], profile: Profile, model: Model) -> list[Ranked]:
    out = []
    for it in items:
        if not it.get("answers"):
            continue
        f = featurize(it, profile)
        out.append(Ranked(it, model.score(f), f))
    out.sort(key=lambda r: r.score, reverse=True)
    return out


def select_digest(ranked: list[Ranked], profile: Profile) -> tuple[list[Ranked], list[Ranked]]:
    """Top-N with diversity caps, plus reserved slots; returns (picks, also_notable).

    `reserve` guarantees a few slots for under-represented interests (e.g. math), filled by
    that topic's best item if it clears the lower `reserve_floor`. Unused reservations fall
    back to the general ranking, so a day with no good math paper doesn't get a bad one.
    """
    d = profile.digest
    caps = d.get("caps", {})
    floor = d.get("min_score", float("-inf"))
    reserve = dict(d.get("reserve", {}))
    reserve_floor = d.get("reserve_floor", floor)
    size = d["size"]

    picks: list[Ranked] = []
    per_topic: dict[str, int] = {}
    per_lab: dict[str, int] = {}
    papers = 0

    def fits(r: Ranked) -> bool:
        topic = r.item["answers"]["topic"]["label"]
        lab = r.item.get("lab")
        is_paper = r.item["source_group"] in ("arxiv", "hf_papers")
        return (per_topic.get(topic, 0) < caps.get("per_topic", 99)
                and (not lab or per_lab.get(lab, 0) < caps.get("per_lab", 99))
                and (not is_paper or papers < caps.get("papers", 99)))

    def take(r: Ranked):
        nonlocal papers
        picks.append(r)
        topic = r.item["answers"]["topic"]["label"]
        per_topic[topic] = per_topic.get(topic, 0) + 1
        if r.item.get("lab"):
            per_lab[r.item["lab"]] = per_lab.get(r.item["lab"], 0) + 1
        papers += r.item["source_group"] in ("arxiv", "hf_papers")

    # 1) reserved slots first, best item per reserved topic
    for topic, n in reserve.items():
        for r in ranked:
            if n <= 0 or len(picks) >= size:
                break
            if r in picks or r.item["answers"]["topic"]["label"] != topic or r.score < reserve_floor:
                continue
            if fits(r):
                take(r)
                n -= 1
    # 2) the rest by score
    for r in ranked:
        if len(picks) >= size or r.score < floor:
            break
        if r not in picks and fits(r):
            take(r)
    picks.sort(key=lambda r: r.score, reverse=True)
    rest = [r for r in ranked if r not in picks and r.score >= floor]
    return picks, rest[: d.get("also_notable", 0)]


def breaking_candidates(ranked: list[Ranked], profile: Profile) -> list[Ranked]:
    b = profile.breaking
    out = []
    for r in ranked:
        a = r.item["answers"]
        p_release = a["kind"]["probs"].get("model_release", 0) + a["kind"]["probs"].get("product_or_api", 0)
        if (r.item.get("lab") and r.item.get("model") != "heuristic"
                and p_release >= b["min_release_prob"]
                and a["significance"]["norm"] >= b["min_significance"]
                and a["substantive"]["p"] >= 0.5):
            out.append(r)
    return out[: b["max_per_run"]]
