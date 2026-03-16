import hashlib
import re
from urllib.parse import urlparse, urlunparse, urlencode, parse_qs

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Article
from app.scrapers.base import RawArticle


def normalize_url(url: str) -> str:
    """Strip tracking params, trailing slashes, utm_ params."""
    try:
        parsed = urlparse(url.strip().rstrip("/"))
        params = parse_qs(parsed.query, keep_blank_values=False)
        # Remove utm_ and tracking params
        cleaned = {k: v for k, v in params.items() if not k.startswith("utm_")}
        new_query = urlencode({k: v[0] for k, v in cleaned.items()}, safe="")
        normalized = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            parsed.params,
            new_query,
            "",  # strip fragment
        ))
        return normalized
    except Exception:
        return url


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()


async def filter_new(session: AsyncSession, raw_articles: list[RawArticle]) -> list[RawArticle]:
    if not raw_articles:
        return []
    hashes = [url_hash(a.url) for a in raw_articles]
    result = await session.execute(
        select(Article.url_hash).where(Article.url_hash.in_(hashes))
    )
    existing_hashes = {row[0] for row in result}
    return [a for a in raw_articles if url_hash(a.url) not in existing_hashes]
