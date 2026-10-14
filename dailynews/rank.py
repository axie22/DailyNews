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

GROUPS = ["lab", "arxiv", "hf_papers", "hf_models", "community"]

PRIOR = {
    "lab": 2.0,
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
}

MIN_LABELS, MIN_PER_CLASS, FULL_TRUST_AT = 15, 5, 60


def feature_names(profile: Profile) -> list[str]:
    return (["lab", "interest", "significance", "substantive", "hf_upvotes"]
            + [f"kind:{k}" for k in profile.kinds]
            + [f"topic:{t}" for t in profile.topics]
            + [f"group:{g}" for g in GROUPS])


def featurize(item: dict, profile: Profile) -> dict[str, float]:
    a = item["answers"]
    weights = profile.topic_weights
    topic_p = a["topic"]["probs"]
    f = {
        "lab": 1.0 if item.get("lab") else 0.0,
        # Expected interest under Jev's topic distribution — uses the full probabilities,
        # not the argmax, so an item that's 40% alignment / 40% agents scores sensibly.
        "interest": sum(weights.get(t, 0.0) * p for t, p in topic_p.items()),
        "significance": float(a["significance"]["norm"]),
        "substantive": float(a["substantive"]["p"]),
        "hf_upvotes": min(1.0, math.log1p(item["meta"].get("hf_upvotes", 0)) / math.log1p(150)),
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
    """Greedy top-N with diversity caps; returns (picks, also_notable)."""
    d = profile.digest
    caps = d.get("caps", {})
    picks, rest = [], []
    per_topic, per_lab, papers = {}, {}, 0
    floor = d.get("min_score", float("-inf"))
    for r in ranked:
        if r.score < floor:
            break  # ranked is sorted, so everything after is below the floor too
        topic = r.item["answers"]["topic"]["label"]
        lab = r.item.get("lab")
        is_paper = r.item["source_group"] in ("arxiv", "hf_papers")
        ok = (len(picks) < d["size"]
              and per_topic.get(topic, 0) < caps.get("per_topic", 99)
              and (not lab or per_lab.get(lab, 0) < caps.get("per_lab", 99))
              and (not is_paper or papers < caps.get("papers", 99)))
        if ok:
            picks.append(r)
            per_topic[topic] = per_topic.get(topic, 0) + 1
            if lab:
                per_lab[lab] = per_lab.get(lab, 0) + 1
            papers += is_paper
        else:
            rest.append(r)
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
