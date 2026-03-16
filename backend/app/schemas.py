import uuid
from datetime import datetime

from pydantic import BaseModel


class ArticleBase(BaseModel):
    id: uuid.UUID
    title: str
    source: str
    summary: str | None
    tags: list[str] | None
    published_at: datetime
    url: str
    authors: list[str] | None

    model_config = {"from_attributes": True}


class ArticleDetail(ArticleBase):
    raw_content: str | None
    source_meta: dict | None
    scraped_at: datetime
    is_summarized: bool


class ArticleListResponse(BaseModel):
    total: int
    articles: list[ArticleBase]


class HealthResponse(BaseModel):
    status: str
    last_pipeline_run: datetime | None
    article_counts: dict[str, int]


class PipelineRunSchema(BaseModel):
    id: uuid.UUID
    run_at: datetime
    duration_ms: int | None
    articles_fetched: int
    articles_stored: int
    errors_json: dict | None

    model_config = {"from_attributes": True}
