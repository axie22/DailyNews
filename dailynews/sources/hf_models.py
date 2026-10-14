from __future__ import annotations

import re

import httpx

from dailynews.sources.base import RawItem, Source
from dailynews.sources.util import parse_iso

HF_MODELS_API = "https://huggingface.co/api/models"

# Variant suffixes collapsed when clustering one release's many repos
# (e.g. Qwen ships -Instruct, -FP8, -AWQ, -GGUF of the same model the same day).
_VARIANT_RE = re.compile(
    r"[-_.]?(instruct|chat|base|it|pt|fp8|fp4|int4|int8|awq|gptq|gguf|mlx|bnb|4bit|8bit|"
    r"thinking|preview|hf|bf16|w4a16|w8a8|nvfp4|onnx|eagle\d*)$",
    re.I,
)


def base_name(model_id: str) -> str:
    """Qwen/Qwen3.8-Flash-Next-FP8 -> Qwen/Qwen3.8-Flash-Next"""
    org, _, name = model_id.partition("/")
    prev = None
    while prev != name:
        prev, name = name, _VARIANT_RE.sub("", name)
    return f"{org}/{name or prev}"


def release_family(model_id: str) -> str:
    return base_name(model_id).lower()


class HFModelsSource(Source):
    def __init__(self, orgs: dict[str, str], min_interval_hours: float = 3.0, per_org: int = 10):
        self.orgs = orgs
        self.per_org = per_org
        self.min_interval_hours = min_interval_hours
        self.key = "hf_models"

    async def fetch(self, client: httpx.AsyncClient) -> list[RawItem]:
        items, errors = [], []
        for org, lab in self.orgs.items():
            try:
                resp = await client.get(HF_MODELS_API, params={
                    "author": org, "sort": "createdAt", "direction": -1, "limit": self.per_org,
                })
                resp.raise_for_status()
            except httpx.HTTPError as e:
                errors.append(f"{org}: {e}")
                continue
            for m in resp.json():
                mid = m.get("id") or m.get("modelId")
                if not mid:
                    continue
                tags = [t for t in (m.get("tags") or []) if ":" not in t][:8]
                base = base_name(mid)
                desc = (f"New model {base} released on Hugging Face by {org}. "
                        f"Task: {m.get('pipeline_tag') or 'unknown'}. Tags: {', '.join(tags)}.")
                items.append(RawItem(
                    url=f"https://huggingface.co/{mid}",
                    title=f"{base} released on Hugging Face",
                    source=self.key,
                    group="hf_models",
                    content=desc,
                    published_at=parse_iso(m.get("createdAt")),
                    lab=lab,
                    meta={"family": release_family(mid), "likes": m.get("likes", 0),
                          "downloads": m.get("downloads", 0), "pipeline_tag": m.get("pipeline_tag")},
                ))
        if errors and not items:
            raise RuntimeError("; ".join(errors))
        return items
