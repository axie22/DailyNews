import hashlib
import logging
import re
from urllib.parse import urlparse, urlunparse, urlencode, parse_qs

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Article
from app.pipeline.arxiv_id import extract_arxiv_id
from app.scrapers.base import RawArticle

logger = logging.getLogger(__name__)


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


async def merge_by_arxiv_id(
    session: AsyncSession, new_articles: list[RawArticle]
) -> list[RawArticle]:
    """For articles sharing an arxiv_id with an existing one, merge provenance
    instead of inserting a duplicate. Returns the subset that should be inserted."""
    to_insert = []
    merged_count = 0

    for raw in new_articles:
        aid = extract_arxiv_id(raw.url)
        if not aid:
            to_insert.append(raw)
            continue

        # Store arxiv_id in source_meta so runner can persist it
        raw.source_meta["arxiv_id"] = aid

        existing_result = await session.execute(
            select(Article).where(Article.arxiv_id == aid).limit(1)
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            # Merge provenance
            meta = existing.source_meta or {}
            provenance = meta.get("also_on", [])
            entry = {"source": raw.source, "url": raw.url}
            if entry not in provenance:
                provenance.append(entry)
                existing.source_meta = {**meta, "also_on": provenance}
            # Carry forward HF upvote count
            if raw.source == "huggingface":
                hf_upvotes = raw.source_meta.get("hf_upvotes")
                if hf_upvotes is not None:
                    existing.source_meta = {**existing.source_meta, "hf_upvotes": hf_upvotes}
            merged_count += 1
        else:
            to_insert.append(raw)

    if merged_count:
        logger.info(f"arXiv dedup: merged {merged_count} duplicates into existing articles")
    return to_insert
