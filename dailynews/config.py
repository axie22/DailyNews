"""Settings (from environment) and the YAML profile/source registry."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

def _find_root() -> Path:
    # Prefer the working directory (a checkout), so a pip-installed package still reads the
    # repo's config/ rather than looking next to site-packages.
    for cand in (Path.cwd(), Path(__file__).resolve().parent.parent):
        if (cand / "config" / "profile.yaml").exists():
            return cand
    return Path.cwd()


ROOT = _find_root()
CONFIG_DIR = Path(os.environ.get("DAILYNEWS_CONFIG_DIR", ROOT / "config"))


@dataclass
class Settings:
    db_path: Path
    typesafe_api_key: str | None
    jev_base_url: str
    # Pinned by default: the learned ranker is trained on Jev's probability outputs,
    # so a silent model upgrade (jev-latest) would shift the feature distribution.
    jev_model: str
    jev_concurrency: int
    telegram_token: str | None
    telegram_chat_id: str | None
    dry_run: bool
    # Cloudflare Worker that receives taps instantly (optional; falls back to Telegram getUpdates).
    worker_url: str | None = None
    worker_token: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            db_path=Path(os.environ.get("DAILYNEWS_DB", ROOT / "state" / "dailynews.db")),
            typesafe_api_key=os.environ.get("TYPESAFE_API_KEY") or None,
            jev_base_url=os.environ.get("JEV_BASE_URL", "https://api.typesafe.ai"),
            jev_model=os.environ.get("JEV_MODEL", "jev-1.13.0"),
            jev_concurrency=int(os.environ.get("JEV_CONCURRENCY", "8")),
            telegram_token=os.environ.get("TELEGRAM_BOT_TOKEN") or None,
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID") or None,
            dry_run=os.environ.get("DAILYNEWS_DRY_RUN", "").lower() in ("1", "true", "yes"),
            worker_url=(os.environ.get("DAILYNEWS_WORKER_URL") or "").strip().rstrip("/") or None,
            worker_token=(os.environ.get("DAILYNEWS_WORKER_TOKEN") or "").strip() or _derived_pull_token(),
        )


def _derived_pull_token() -> str | None:
    from dailynews.derived import derive
    return derive("pull")


@dataclass
class Profile:
    raw: dict
    tz: ZoneInfo = field(init=False)

    def __post_init__(self):
        self.tz = ZoneInfo(self.raw.get("timezone", "America/New_York"))

    @property
    def digest(self) -> dict:
        return self.raw["digest"]

    @property
    def breaking(self) -> dict:
        return self.raw["breaking"]

    @property
    def topics(self) -> dict[str, dict]:
        return self.raw["topics"]

    @property
    def kinds(self) -> dict[str, str]:
        return self.raw["kinds"]

    @property
    def significance_levels(self) -> list[str]:
        return self.raw["significance_levels"]

    @property
    def topic_weights(self) -> dict[str, float]:
        return {k: float(v.get("weight", 0.0)) for k, v in self.topics.items()}


def load_profile(path: Path | None = None) -> Profile:
    return Profile(yaml.safe_load((path or CONFIG_DIR / "profile.yaml").read_text()))


def load_sources(path: Path | None = None) -> dict:
    return yaml.safe_load((path or CONFIG_DIR / "sources.yaml").read_text())
