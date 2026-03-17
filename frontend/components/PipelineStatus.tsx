"use client";

import { useState, useEffect } from "react";
import { getPipelineStatus, PipelineStatusResponse } from "@/lib/api";

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
}

const PHASE_LABELS: Record<string, string> = {
  idle: "Idle",
  scraping: "Scraping sources",
  summarizing: "Summarizing articles",
  recommending: "Generating recommendations",
};

export default function PipelineStatus() {
  const [status, setStatus] = useState<PipelineStatusResponse | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const data = await getPipelineStatus();
        if (active) setStatus(data);
      } catch {
        // Backend not reachable
      }
    };
    poll();
    const interval = setInterval(poll, 3000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  if (!status) return null;

  const isActive = status.phase !== "idle";
  const hasWarning =
    !isActive &&
    (status.ollama_status === "unavailable" || status.ollama_status === "pulling") &&
    status.unsummarized_count > 0;
  const hasErrors = !isActive && status.recent_errors.length > 0 && status.unsummarized_count > 0;

  // Hide when idle with no issues
  if (!isActive && !hasWarning && !hasErrors) return null;

  const { summarization: s, recommendation: r } = status;
  const progress = s.total > 0 ? Math.round((s.done / s.total) * 100) : 0;

  // Warning state: idle but Ollama unavailable with pending articles
  if (!isActive && (hasWarning || hasErrors)) {
    return (
      <div className="mb-4 border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950 rounded-xl overflow-hidden">
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full px-4 py-2.5 flex items-center gap-3 text-left hover:bg-amber-100/50 transition-colors"
        >
          {/* Warning icon */}
          <svg className="w-4 h-4 text-amber-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>

          <span className="text-xs font-medium text-amber-700">
            {status.ollama_status === "pulling"
              ? `Pulling model — ${status.unsummarized_count} articles waiting`
              : status.ollama_status === "unavailable"
              ? `Ollama unavailable — ${status.unsummarized_count} articles waiting for summarization`
              : `${status.unsummarized_count} articles pending`}
          </span>

          <svg
            className={`w-3.5 h-3.5 text-amber-400 ml-auto transition-transform ${expanded ? "rotate-180" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {expanded && (
          <div className="px-4 py-3 border-t border-amber-200 space-y-2 text-xs">
            <div className="flex items-center gap-2">
              <span className="text-amber-400 w-20">Ollama</span>
              <span className={`font-medium ${
                status.ollama_status === "unavailable" ? "text-red-600" :
                status.ollama_status === "pulling" ? "text-amber-600" :
                "text-gray-500"
              }`}>
                {status.ollama_status}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-amber-400 w-20">Pending</span>
              <span className="text-amber-700">
                {status.unsummarized_count} articles need summarization
              </span>
            </div>
            <p className="text-amber-600 pt-1">
              Summarization will resume automatically when the pipeline next runs, or you can trigger it manually.
            </p>

            {status.recent_errors.length > 0 && (
              <div className="mt-2 pt-2 border-t border-amber-200">
                <div className="text-red-500 font-medium mb-1">Recent errors</div>
                {status.recent_errors.map((err, i) => (
                  <div key={i} className="text-red-400 truncate" title={err}>
                    {err}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  // Active pipeline state (blue banner)
  return (
    <div className="mb-4 border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950 rounded-xl overflow-hidden">
      {/* Compact bar */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-2.5 flex items-center gap-3 text-left hover:bg-blue-100/50 transition-colors"
      >
        {/* Spinner */}
        <span className="w-4 h-4 border-2 border-blue-300 border-t-blue-600 rounded-full animate-spin flex-shrink-0" />

        {/* Phase label */}
        <span className="text-xs font-medium text-blue-700">
          {PHASE_LABELS[status.phase] || status.phase}
        </span>

        {/* Progress */}
        {status.phase === "summarizing" && s.total > 0 && (
          <>
            <span className="text-xs text-blue-500">
              {s.done}/{s.total} articles ({progress}%)
            </span>
            {status.eta_s != null && status.eta_s > 0 && (
              <span className="text-xs text-blue-400">
                ~{formatDuration(status.eta_s)} remaining
              </span>
            )}
          </>
        )}

        {r.recommended > 0 && (
          <span className="text-xs text-blue-500">
            {r.recommended} recommended
          </span>
        )}

        {/* Elapsed */}
        {status.elapsed_s != null && (
          <span className="text-xs text-blue-400 ml-auto">
            {formatDuration(status.elapsed_s)}
          </span>
        )}

        {/* Expand chevron */}
        <svg
          className={`w-3.5 h-3.5 text-blue-400 transition-transform ${expanded ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Progress bar */}
      {status.phase === "summarizing" && s.total > 0 && (
        <div className="h-1 bg-blue-100">
          <div
            className="h-full bg-blue-500 transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      {/* Expanded details */}
      {expanded && (
        <div className="px-4 py-3 border-t border-blue-200 space-y-2 text-xs">
          {/* Ollama */}
          <div className="flex items-center gap-2">
            <span className="text-blue-400 w-20">Ollama</span>
            <span className={`font-medium ${
              status.ollama_status === "ready" ? "text-green-600" :
              status.ollama_status === "waiting" ? "text-amber-600" :
              status.ollama_status === "pulling" ? "text-amber-600" :
              status.ollama_status === "unavailable" ? "text-red-600" :
              "text-gray-500"
            }`}>
              {status.ollama_status === "pulling" ? "pulling model..." : status.ollama_status}
            </span>
          </div>

          {/* Scrape */}
          {status.scrape.articles_fetched > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-blue-400 w-20">Scraped</span>
              <span className="text-blue-700">
                {status.scrape.articles_fetched} fetched, {status.scrape.articles_stored} new
              </span>
            </div>
          )}

          {/* Summarization */}
          {s.total > 0 && (
            <>
              <div className="flex items-center gap-2">
                <span className="text-blue-400 w-20">Summaries</span>
                <span className="text-blue-700">
                  {s.done}/{s.total} done
                  {s.failures > 0 && <span className="text-red-500 ml-1">({s.failures} failed)</span>}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-blue-400 w-20">Batch</span>
                <span className="text-blue-700">
                  {s.batch} | last: {s.last_batch_s}s | avg: {s.avg_batch_s}s
                </span>
              </div>
            </>
          )}

          {/* Recommendations */}
          {r.recommended > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-blue-400 w-20">Picks</span>
              <span className="text-blue-700">
                Top {r.recommended} articles by relevance score
              </span>
            </div>
          )}

          {/* Errors */}
          {status.recent_errors.length > 0 && (
            <div className="mt-2 pt-2 border-t border-blue-200">
              <div className="text-red-500 font-medium mb-1">Recent errors</div>
              {status.recent_errors.map((err, i) => (
                <div key={i} className="text-red-400 truncate" title={err}>
                  {err}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
