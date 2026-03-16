import uuid
from datetime import datetime

from sqlalchemy import Boolean, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.types import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    authors: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    published_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    scraped_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    source_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_summarized: Mapped[bool] = mapped_column(Boolean, default=False)
    relevance_score: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    is_recommended: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)

    __table_args__ = (
        Index("ix_articles_source", "source"),
        Index("ix_articles_published_at", "published_at"),
        Index("ix_articles_tags", "tags", postgresql_using="gin"),
    )


class ScraperState(Base):
    __tablename__ = "scraper_state"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    articles_fetched: Mapped[int] = mapped_column(default=0)
    articles_stored: Mapped[int] = mapped_column(default=0)
    errors_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
