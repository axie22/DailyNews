import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from app.config import settings
from app.pipeline.runner import run_pipeline, run_x_pipeline

logger = logging.getLogger(__name__)


def start_scheduler(app: FastAPI) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        run_pipeline,
        trigger="interval",
        hours=settings.pipeline_interval_hours,
        id="pipeline",
        replace_existing=True,
        next_run_time=datetime.now(),
    )

    scheduler.add_job(
        run_x_pipeline,
        trigger="interval",
        hours=settings.x_scrape_interval_hours,
        id="x_pipeline",
        replace_existing=True,
        next_run_time=datetime.now(),
    )

    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("Scheduler started")
    return scheduler
