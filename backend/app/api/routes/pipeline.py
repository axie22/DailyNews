from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import func, select

from app.database import async_session_factory
from app.models import Article
from app.pipeline.runner import run_pipeline
from app.pipeline.status import pipeline_status

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.post("/trigger")
async def trigger_pipeline(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_pipeline)
    return {"status": "pipeline triggered"}


@router.get("/status")
async def get_pipeline_status():
    # Include live unsummarized count so frontend can show warnings when idle
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count())
            .select_from(Article)
            .where(Article.is_summarized == False)  # noqa: E712
        )
        unsummarized = result.scalar_one()
    data = pipeline_status.to_dict()
    data["unsummarized_count"] = unsummarized
    return data
