"""The Jev question set, built from config/profile.yaml.

The question set is hashed into a `qset` id. Features are stored with that id and the
learned ranker only trains on features from the current qset, because rewording a
question shifts Jev's output distribution and makes old features incomparable.
"""
from __future__ import annotations

import hashlib
import json

from dailynews.config import Profile

STATE_CHARS = 1500  # ~400 tokens of item text; abstracts rarely need more for triage


def build_questions(profile: Profile) -> dict:
    return {
        "kind": {
            "type": "choice",
            "instructions": "What kind of item is this?",
            "criteria": dict(profile.kinds),
        },
        "topic": {
            "type": "choice",
            "instructions": "Which research area is this item primarily about?",
            "criteria": {k: v["description"] for k, v in profile.topics.items()},
        },
        "significance": {
            "type": "score",
            "instructions": ("How significant is this for an ML researcher or engineer who follows the "
                             "field closely? Judge the substance of what is reported, not the tone or hype."),
            "criteria": list(profile.significance_levels),
        },
        "substantive": {
            "type": "noul",
            "instructions": "Does this item contain substantive technical or factual content?",
            "criteria": {
                "true": "Concrete new results, methods, model or product releases, or technical detail",
                "false": "Hype, marketing, recycled news, listicle, vague teaser, or a question/help post",
            },
        },
    }


def qset_id(questions: dict) -> str:
    return hashlib.sha1(json.dumps(questions, sort_keys=True).encode()).hexdigest()[:10]


SOURCE_LABELS = {
    "arxiv": "arXiv preprint",
    "hf_papers": "Hugging Face Daily Papers",
    "hf_models": "Hugging Face model hub",
}


def build_state(item: dict) -> str:
    """The text Jev evaluates. Deliberately omits our own priority flags/upvotes:
    those are separate ranking features, and leaking them in would double-count."""
    src = SOURCE_LABELS.get(item["source_group"], item["source"].replace("_", " "))
    parts = [f"Source: {src}", f"Title: {item['title']}"]
    content = (item.get("content") or "").strip()
    if content:
        parts.append(f"Text: {content[:STATE_CHARS]}")
    return "\n".join(parts)
