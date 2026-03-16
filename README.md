# ML News Aggregator

A personal ML news aggregator that runs a scheduled pipeline every 6 hours to scrape articles and papers from multiple sources, deduplicates them, summarizes them via a local Ollama model, stores them in Postgres, and serves them through a Next.js frontend styled like TLDR.

## Tech Stack

| Layer       | Technology                                    |
| ----------- | --------------------------------------------- |
| Scrapers    | Python 3.12, `httpx`, `feedparser`, `bs4`     |
| Scheduler   | APScheduler (in-process)                      |
| Summarizer  | Ollama HTTP API (`qwen3:8b`)                |
| Database    | PostgreSQL 16 via `asyncpg` + SQLAlchemy 2    |
| Backend API | FastAPI + Uvicorn                             |
| Frontend    | Next.js 14 (App Router), TypeScript, Tailwind |
| Dev env     | Docker Compose (Postgres + Ollama containers) |

## Sources

- **arXiv** — cs.LG, cs.AI, cs.CL categories (top 50 by submission date)
- **Hugging Face Papers** — trending papers from huggingface.co/papers
- **RSS Feeds** — OpenAI, Anthropic, DeepMind, Meta AI, BAIR, Reddit r/MachineLearning
- **X/Twitter API** — curated list of high-signal ML accounts (optional, requires bearer token)

## Environment Setup Checklist

```bash
# 1. Start infra
docker compose up -d postgres ollama

# 2. Pull the summarization model
docker compose exec ollama ollama pull qwen3:8b

# 3. Install backend deps
cd backend && uv sync

# 4. Copy and configure environment
cp backend/.env.example backend/.env
# Edit backend/.env — set X_BEARER_TOKEN if using X/Twitter scraper

# 5. Run database migrations
cd backend && alembic upgrade head

# 6. Test pipeline manually
python -m app.pipeline.runner

# 7. Start backend
uvicorn app.main:app --reload --port 8000

# 8. Start frontend (separate terminal)
cd frontend && npm install && npm run dev
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs

## Running with Docker Compose (all services)

```bash
cp backend/.env.example backend/.env
docker compose up --build
```

Then pull the model and run the initial migration:

```bash
docker compose exec ollama ollama pull qwen3:8b
docker compose exec backend alembic upgrade head
```

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entrypoint + lifespan
│   │   ├── config.py            # Pydantic settings (reads .env)
│   │   ├── database.py          # SQLAlchemy async engine + session
│   │   ├── models.py            # ORM models (Article, ScraperState, PipelineRun)
│   │   ├── schemas.py           # Pydantic response schemas
│   │   ├── api/routes/
│   │   │   ├── articles.py      # GET /api/articles, /api/articles/:id, /api/articles/tags
│   │   │   ├── health.py        # GET /api/health, /api/health/runs
│   │   │   └── pipeline.py      # POST /api/pipeline/trigger
│   │   ├── scrapers/
│   │   │   ├── arxiv.py         # arXiv Atom API scraper
│   │   │   ├── huggingface.py   # HF Papers HTML scraper
│   │   │   ├── rss.py           # Generic RSS feed scraper
│   │   │   └── x_api.py         # X API v2 scraper (cost-managed)
│   │   └── pipeline/
│   │       ├── runner.py        # Orchestrates scrape → dedup → summarize → store
│   │       ├── dedup.py         # URL normalization + hash-based deduplication
│   │       └── summarizer.py    # Ollama qwen3 summarization with retry
│   ├── scheduler.py             # APScheduler setup (6hr pipeline + 24hr X pipeline)
│   ├── migrations/              # Alembic migration files
│   ├── alembic.ini
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── app/
│   │   ├── layout.tsx           # Root layout with sticky header
│   │   ├── page.tsx             # Main feed page with filtering + pagination
│   │   └── article/[id]/        # Article detail page
│   ├── components/
│   │   ├── ArticleCard.tsx      # Card with source badge, tags, summary, time-ago
│   │   ├── FilterBar.tsx        # Source + tag + search filter UI
│   │   └── TagBadge.tsx         # Color-coded topic tag badge
│   ├── lib/api.ts               # Typed fetch wrapper for backend API
│   └── types/article.ts         # Shared TypeScript interfaces
└── docker-compose.yml
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/articles` | List articles with filtering (`source`, `tags`, `q`, `since`, `limit`, `offset`) |
| GET | `/api/articles/tags` | Tag counts for filter bar |
| GET | `/api/articles/:id` | Full article detail |
| GET | `/api/health` | Pipeline status + article counts by source |
| GET | `/api/health/runs` | Recent pipeline run history |
| POST | `/api/pipeline/trigger` | Manually trigger a pipeline run |

## Configuration

All configuration is via environment variables (see `backend/.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | postgres://mlnews:mlnews@localhost:5432/mlnews | PostgreSQL connection string |
| `OLLAMA_BASE_URL` | http://localhost:11434 | Ollama API base URL |
| `OLLAMA_MODEL` | qwen3:8b | Model to use for summarization |
| `PIPELINE_INTERVAL_HOURS` | 6 | How often to run the main pipeline |
| `X_BEARER_TOKEN` | (empty) | X/Twitter API bearer token — scraper is skipped if not set |
| `X_MONTHLY_TWEET_CAP` | 10000 | Hard monthly tweet read limit to protect API budget |
| `X_SCRAPE_INTERVAL_HOURS` | 24 | How often to run the X scraper |
