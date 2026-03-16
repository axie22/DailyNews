from fastapi import APIRouter, BackgroundTasks

from app.pipeline.runner import run_pipeline

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.post("/trigger")
async def trigger_pipeline(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_pipeline)
    return {"status": "pipeline triggered"}
