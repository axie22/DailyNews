from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Article
from app.schemas import ArticleDetail, ArticleListResponse

router = APIRouter(prefix="/api/articles", tags=["articles"])


@router.get("", response_model=ArticleListResponse)
async def list_articles(
    source: str | None = None,
    tags: str | None = None,
    limit: int = Query(default=20, le=100),
    offset: int = 0,
    since: str | None = None,
    q: str | None = None,
    recommended: bool | None = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Article)

    if recommended is not None and recommended:
        stmt = stmt.where(Article.is_recommended == True)  # noqa: E712

    if source:
        stmt = stmt.where(Article.source == source)

    if tags:
        tag_list = [t.strip() for t in tags.split(",")]
        stmt = stmt.where(Article.tags.overlap(tag_list))

    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            stmt = stmt.where(Article.published_at >= since_dt)
        except ValueError:
            pass
    else:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)
        stmt = stmt.where(Article.published_at >= cutoff)

    if q:
        stmt = stmt.where(
            (Article.title.ilike(f"%{q}%")) | (Article.summary.ilike(f"%{q}%"))
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(Article.published_at.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    articles = result.scalars().all()

    return ArticleListResponse(total=total, articles=list(articles))


@router.get("/tags")
async def list_tags(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Article.tags).where(Article.tags.isnot(None))
    )
    tag_counts: dict[str, int] = {}
    for (tags,) in result:
        if tags:
            for tag in tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
    return sorted(tag_counts.items(), key=lambda x: -x[1])


@router.get("/{article_id}", response_model=ArticleDetail)
async def get_article(article_id: str, session: AsyncSession = Depends(get_session)):
    import uuid
    from fastapi import HTTPException
    try:
        uid = uuid.UUID(article_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid article ID")
    article = await session.get(Article, uid)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article
