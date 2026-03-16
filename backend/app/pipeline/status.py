"""Pipeline status tracking — in-memory state for live progress visibility."""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class PipelineStatus:
    phase: str = "idle"  # idle, scraping, summarizing, recommending
    started_at: float | None = None

    # Scrape stats
    articles_fetched: int = 0
    articles_stored: int = 0

    # Summarization stats
    total_to_summarize: int = 0
    summarized: int = 0
    summary_failures: int = 0
    current_batch: int = 0
    total_batches: int = 0
    last_batch_duration_s: float = 0
    avg_batch_duration_s: float = 0

    # Recommendation stats
    recommended: int = 0

    # Ollama
    ollama_status: str = "unknown"  # unknown, waiting, ready, unavailable

    # Errors
    recent_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        elapsed = None
        if self.started_at:
            elapsed = round(time.monotonic() - self.started_at, 1)

        eta_s = None
        if (
            self.phase == "summarizing"
            and self.avg_batch_duration_s > 0
            and self.current_batch > 0
        ):
            remaining_batches = self.total_batches - self.current_batch
            eta_s = round(remaining_batches * self.avg_batch_duration_s)

        return {
            "phase": self.phase,
            "elapsed_s": elapsed,
            "eta_s": eta_s,
            "ollama_status": self.ollama_status,
            "scrape": {
                "articles_fetched": self.articles_fetched,
                "articles_stored": self.articles_stored,
            },
            "summarization": {
                "total": self.total_to_summarize,
                "done": self.summarized,
                "failures": self.summary_failures,
                "batch": f"{self.current_batch}/{self.total_batches}",
                "last_batch_s": round(self.last_batch_duration_s, 1),
                "avg_batch_s": round(self.avg_batch_duration_s, 1),
            },
            "recommendation": {
                "recommended": self.recommended,
            },
            "recent_errors": self.recent_errors[-5:],
        }

    def add_error(self, msg: str):
        self.recent_errors.append(msg)
        if len(self.recent_errors) > 20:
            self.recent_errors = self.recent_errors[-20:]

    def reset(self):
        self.phase = "idle"
        self.started_at = None
        self.articles_fetched = 0
        self.articles_stored = 0
        self.total_to_summarize = 0
        self.summarized = 0
        self.summary_failures = 0
        self.current_batch = 0
        self.total_batches = 0
        self.last_batch_duration_s = 0
        self.avg_batch_duration_s = 0
        self.recommended = 0
        self.ollama_status = "unknown"
        self.recent_errors = []


# Singleton — shared across the pipeline
pipeline_status = PipelineStatus()
