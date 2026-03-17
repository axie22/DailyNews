import type { Article, ArticleDetail, ArticleListResponse, ArticleQueryParams } from "@/types/article";

// Browser (client components): reaches the host backend directly via localhost.
// SSR inside Docker (server components): localhost means the container itself,
// so use host.docker.internal to reach the backend running on the host machine.
const API_BASE =
  typeof window === "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://host.docker.internal:8000")
    : "http://localhost:8000";

export async function getArticles(params: ArticleQueryParams): Promise<ArticleListResponse> {
  const query = new URLSearchParams(
    Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== "")) as Record<string, string>
  ).toString();
  const res = await fetch(`${API_BASE}/api/articles${query ? `?${query}` : ""}`, {
    next: { revalidate: 60 },
  });
  if (!res.ok) throw new Error("Failed to fetch articles");
  return res.json();
}

export async function getArticle(id: string): Promise<ArticleDetail> {
  const res = await fetch(`${API_BASE}/api/articles/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Article not found");
  return res.json();
}

export async function getRelated(id: string): Promise<ArticleListResponse> {
  const res = await fetch(`${API_BASE}/api/articles/${id}/related?limit=3`, { cache: "no-store" });
  if (!res.ok) return { total: 0, articles: [] };
  return res.json();
}

export async function getTags(): Promise<[string, number][]> {
  const res = await fetch(`${API_BASE}/api/articles/tags`, { next: { revalidate: 300 } });
  if (!res.ok) return [];
  return res.json();
}

export interface PipelineStatusResponse {
  phase: string;
  elapsed_s: number | null;
  eta_s: number | null;
  ollama_status: string;
  unsummarized_count: number;
  scrape: {
    articles_fetched: number;
    articles_stored: number;
  };
  summarization: {
    total: number;
    done: number;
    failures: number;
    batch: string;
    last_batch_s: number;
    avg_batch_s: number;
  };
  recommendation: {
    recommended: number;
  };
  recent_errors: string[];
}

export async function getPipelineStatus(): Promise<PipelineStatusResponse> {
  const res = await fetch(`${API_BASE}/api/pipeline/status`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch pipeline status");
  return res.json();
}
