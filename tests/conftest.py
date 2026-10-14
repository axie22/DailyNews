import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from dailynews.config import Settings, load_profile, load_sources  # noqa: E402
from dailynews.sources import build_sources  # noqa: E402
from fakeweb import FakeWeb  # noqa: E402

# 08:00 New York (EDT) on the day this was written
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def now():
    return NOW


@pytest.fixture
def web():
    return FakeWeb(NOW)


@pytest.fixture
def profile():
    return load_profile()


@pytest.fixture
def sources():
    cfg = load_sources()
    # keep only sources the fake web serves
    cfg["rss"] = [s for s in cfg["rss"] if s["key"] == "openai"]
    cfg["anthropic"] = [s for s in cfg["anthropic"] if s["key"] == "anthropic_news"]
    return build_sources(cfg)


@pytest.fixture
def settings(tmp_path):
    return Settings(db_path=tmp_path / "state" / "t.db", typesafe_api_key="test-key",
                    jev_base_url="https://api.typesafe.ai", jev_model="jev-1.13.0", jev_concurrency=4,
                    telegram_token="TOKEN", telegram_chat_id="42", dry_run=False)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    import asyncio

    real_sleep = asyncio.sleep

    async def fast(_s, *a, **k):
        await real_sleep(0)
    monkeypatch.setattr("dailynews.classify.jev.asyncio.sleep", fast)
    monkeypatch.setattr("dailynews.telegram.asyncio.sleep", fast)
