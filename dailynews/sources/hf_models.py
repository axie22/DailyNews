from __future__ import annotations

import re

import httpx

from dailynews.sources.base import RawItem, Source
from dailynews.sources.util import parse_iso

HF_MODELS_API = "https://huggingface.co/api/models"

# Variant suffixes collapsed when clustering one release's many repos
# (Qwen ships -Instruct, -FP8, -AWQ, -GGUF of the same model the same day; NVIDIA ships
# -NVFP4-LiLiCorr, -MX, -DFlash2 builds).
_VARIANT_RE = re.compile(
    r"[-_.]?(instruct|chat|base|it|pt|fp8|fp4|nvfp4|mxfp4|int4|int8|awq|gptq|gguf|mlx|bnb|4bit|8bit|"
    r"thinking|preview|hf|bf16|w4a16|w8a8|onnx|eagle\d*|mx|lilicorr|dflash\d*|\d+gb)$",
    re.I,
)
# Parameter-count tokens: "-72B", "-5M", "-120B-A12B", "-30B-A3B". Sizes of one release share a family.
_SIZE_RE = re.compile(r"[-_.]\d+(?:\.\d+)?[MBT](?:[-_.]A\d+(?:\.\d+)?[MB])?(?=$|[-_.])", re.I)

# Training artifacts, not releases: checkpoints, exports, sweeps, internal experiments.
JUNK_RE = re.compile(
    r"(checkpoint|ckpt|[-_]step[-_]?\d|[-_]iter\d|[-_]epoch|export|[-_]sdg[-_]|[-_]s\d+_|[-_]seed\d|"
    r"debug|test|tmp|sweep|ablation|[-_]exp\d|sim2real|libero|[-_]v\d+[-_]\d{5,})",
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
    """Size-agnostic: mistralai/Timestral-5M and -28M -> mistralai/timestral"""
    org, _, name = base_name(model_id).partition("/")
    name = _SIZE_RE.sub("", name) or name
    return f"{org}/{name}".lower()


def is_junk(model_id: str) -> bool:
    return bool(JUNK_RE.search(model_id.partition("/")[2]))


class HFModelsSource(Source):
    """New model repos from frontier orgs: catches open-weight releases with no blog post.

    Filters: training artifacts are dropped by name; orgs that upload constantly (NVIDIA)
    can require some community traction (`min_likes`). Repos are re-fetched each run, so one
    below the bar today simply appears once it earns the likes.
    """

    def __init__(self, orgs: dict[str, str], min_interval_hours: float = 3.0, per_org: int = 25,
                 min_likes: dict[str, int] | None = None):
        self.orgs = orgs
        self.per_org = per_org
        self.min_likes = min_likes or {}
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
            floor = int(self.min_likes.get(org, 0))
            for m in resp.json():
                mid = m.get("id") or m.get("modelId")
                if not mid or is_junk(mid) or int(m.get("likes") or 0) < floor:
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
