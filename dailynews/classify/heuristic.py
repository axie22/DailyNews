"""Zero-cost fallback used when Jev is unavailable (no key, outage, auth failure).

Deliberately crude: it keeps the digest flowing, and items it labels are re-classified
by Jev on the next run where Jev works (they're never used as training data).
"""
from __future__ import annotations

import re

from dailynews.config import Profile

_RELEASE = re.compile(r"\b(introduc\w*|releas\w*|launch\w*|now available|announc\w*|open[- ]sourc\w*)\b", re.I)
_SAFETY = re.compile(r"\b(safety|alignment|policy|responsib\w*|governance|red[- ]team\w*)\b", re.I)
_TOOL = re.compile(r"\b(library|framework|toolkit|dataset|benchmark|sdk|open[- ]source)\b", re.I)
_WORD = re.compile(r"[a-z]{4,}")


def _softmax_like(scores: dict[str, float]) -> dict[str, float]:
    total = sum(scores.values()) or 1.0
    return {k: v / total for k, v in scores.items()}


def classify(item: dict, profile: Profile) -> dict:
    text = f"{item['title']} {item.get('content', '')}".lower()
    words = set(_WORD.findall(text))

    group = item["source_group"]
    kind = {k: 0.05 for k in profile.kinds}
    if group in ("arxiv", "hf_papers"):
        kind["research_paper"] = 2.0
    elif group == "hf_models":
        kind["model_release"] = 2.0
    elif item["source"].startswith("reddit"):
        kind["discussion_opinion"] = 1.0
    else:
        if _RELEASE.search(text):
            kind["product_or_api"] = 0.8
            kind["model_release"] = 0.6
        if _SAFETY.search(text):
            kind["safety_policy"] = 0.7
        if _TOOL.search(text):
            kind["tooling_infra"] = 0.5
        kind["other_news"] = max(kind["other_news"], 0.3)
    kind = {k: v for k, v in kind.items() if k in profile.kinds}

    topic = {}
    for name, spec in profile.topics.items():
        vocab = set(_WORD.findall(spec["description"].lower()))
        topic[name] = 0.05 + len(words & vocab)
    topic_p = _softmax_like(topic)

    sig = 1.0 + (0.5 if item.get("lab") else 0.0)
    levels = len(profile.significance_levels)
    kind_p = _softmax_like(kind)
    return {
        "kind": {"label": max(kind_p, key=kind_p.get), "probs": kind_p, "confidence": None},
        "topic": {"label": max(topic_p, key=topic_p.get), "probs": topic_p, "confidence": None},
        "significance": {"score": sig, "norm": sig / max(1, levels - 1), "probs": {}, "confidence": None},
        "substantive": {"p": 0.6},
    }
