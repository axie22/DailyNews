from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Article, PipelineRun
from app.schemas import HealthResponse, PipelineRunSchema

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("", response_model=HealthResponse)
async def health(session: AsyncSession = Depends(get_session)):
    last_run_result = await session.execute(
        select(PipelineRun.run_at).order_by(PipelineRun.run_at.desc()).limit(1)
    )
    last_run = last_run_result.scalar_one_or_none()

    counts_result = await session.execute(
        select(Article.source, func.count(Article.id)).group_by(Article.source)
    )
    article_counts = dict(counts_result.all())

    return HealthResponse(
        status="ok",
        last_pipeline_run=last_run,
        article_counts=article_counts,
    )


@router.get("/runs", response_model=list[PipelineRunSchema])
async def pipeline_runs(
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(PipelineRun).order_by(PipelineRun.run_at.desc()).limit(limit)
    )
    return result.scalars().all()
