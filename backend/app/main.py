import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import articles, health, pipeline
from app.api.routes.seen import router as seen_router
from app.config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from scheduler import start_scheduler
    start_scheduler(app)
    yield
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown()


app = FastAPI(title="ML News API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(articles.router)
app.include_router(health.router)
app.include_router(pipeline.router)
app.include_router(seen_router)
