import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI

from app.config import settings
from app.pipeline.runner import resume_processing, run_pipeline, run_x_pipeline

logger = logging.getLogger(__name__)


def start_scheduler(app: FastAPI) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    # Main pipeline: every 6 hours + guaranteed 8am daily
    # Does NOT fire on startup — startup only resumes summarization/recommendation
    scheduler.add_job(
        run_pipeline,
        trigger="interval",
        hours=settings.pipeline_interval_hours,
        id="pipeline_interval",
        replace_existing=True,
    )
    scheduler.add_job(
        run_pipeline,
        trigger=CronTrigger(hour=8, minute=0),
        id="pipeline_morning",
        replace_existing=True,
    )

    # X pipeline: once daily at 8am
    scheduler.add_job(
        run_x_pipeline,
        trigger=CronTrigger(hour=8, minute=0),
        id="x_pipeline_morning",
        replace_existing=True,
    )

    # On startup: only resume summarization + recommendation for existing backlog
    # No scraping — avoids redundant fetches on every restart
    scheduler.add_job(
        resume_processing,
        id="startup_resume",
        replace_existing=True,
        next_run_time=datetime.now(),
    )

    scheduler.start()
    app.state.scheduler = scheduler
    logger.info(
        "Scheduler started — scrape: every %dh + 8am, X: daily 8am, "
        "startup: resume summarization only",
        settings.pipeline_interval_hours,
    )
    return scheduler
