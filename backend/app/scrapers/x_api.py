import asyncio
import logging
from datetime import datetime, timezone

from app.config import settings
from app.scrapers.base import BaseScraper, RawArticle

logger = logging.getLogger(__name__)

def _is_meaningful_title(text: str) -> bool:
    """Return False if the tweet is just a URL or has no substantive content."""
    import re
    stripped = re.sub(r"https?://\S+", "", text).strip()
    return len(stripped) >= 20


X_ACCOUNTS = [
    "_akhaliq",
    "hardmaru",
    "ylecun",
    "karpathy",
    "DrJimFan",
    "GaryMarcus",
    "ClementDelangue",
    "jeremyphoward",
    "fchollet",
    "ggerganov",
    "rasbt",
    "srush_nlp",
    "nvidia"
]


class XApiScraper(BaseScraper):
    def __init__(self, session, dry_run: bool = False):
        self.session = session
        self.dry_run = dry_run
        self._client = None

    def _get_client(self):
        if self._client is None:
            import tweepy
            self._client = tweepy.Client(bearer_token=settings.x_bearer_token)
        return self._client

    async def _get_state(self, key: str) -> str | None:
        from app.models import ScraperState
        row = await self.session.get(ScraperState, key)
        return row.value if row else None

    async def _set_state(self, key: str, value: str):
        from app.models import ScraperState
        await self.session.merge(ScraperState(key=key, value=value))

    async def _check_budget(self, batch_size: int) -> bool:
        month_key = f"x_monthly_count_{datetime.now().strftime('%Y_%m')}"
        used = int(await self._get_state(month_key) or "0")
        if used + batch_size > settings.x_monthly_tweet_cap:
            logger.warning(
                f"X API monthly cap reached ({used}/{settings.x_monthly_tweet_cap}). "
                "Skipping until next month."
            )
            return False
        return True

    async def fetch(self) -> list[RawArticle]:
        if not settings.x_bearer_token:
            logger.info("X_BEARER_TOKEN not set, skipping X scraper")
            return []

        since_id = await self._get_state("x_since_id")
        query = " OR ".join(f"from:{acct}" for acct in X_ACCOUNTS)
        query += " -is:retweet has:links"

        if not await self._check_budget(100):
            return []

        client = self._get_client()
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.search_recent_tweets(
                query=query,
                since_id=since_id,
                max_results=100,
                tweet_fields=["created_at", "author_id", "entities", "public_metrics"],
                expansions=["author_id"],
                user_fields=["username"],
            ),
        )

        if not response.data:
            return []

        newest_id = str(max(int(t.id) for t in response.data))

        if not self.dry_run:
            await self._set_state("x_since_id", newest_id)
            month_key = f"x_monthly_count_{datetime.now().strftime('%Y_%m')}"
            used = int(await self._get_state(month_key) or "0")
            await self._set_state(month_key, str(used + len(response.data)))

        users = {u.id: u.username for u in (response.includes.get("users") or [])}

        articles = []
        for tweet in response.data:
            urls = tweet.entities.get("urls", []) if tweet.entities else []
            external_urls = [
                u["expanded_url"]
                for u in urls
                if not u["expanded_url"].startswith("https://t.co")
                and "twitter.com" not in u["expanded_url"]
                and "x.com" not in u["expanded_url"]
            ]
            if not external_urls:
                continue

            if not _is_meaningful_title(tweet.text):
                logger.debug(f"Skipping low-content tweet {tweet.id}: {tweet.text[:60]}")
                continue

            articles.append(
                RawArticle(
                    url=external_urls[0],
                    title=tweet.text[:120],
                    source="x",
                    published_at=tweet.created_at.replace(tzinfo=timezone.utc)
                    if tweet.created_at
                    else datetime.now(tz=timezone.utc),
                    raw_content=tweet.text,
                    authors=[users.get(tweet.author_id, "unknown")],
                    source_meta={
                        "tweet_id": str(tweet.id),
                        "author": users.get(tweet.author_id),
                        "likes": tweet.public_metrics.get("like_count", 0),
                        "retweets": tweet.public_metrics.get("retweet_count", 0),
                    },
                )
            )

        logger.info(f"X API: fetched {len(response.data)} tweets → {len(articles)} with links")
        return articles
