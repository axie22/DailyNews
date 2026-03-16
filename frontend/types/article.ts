export interface Article {
  id: string;
  title: string;
  source: string;
  summary: string | null;
  tags: string[] | null;
  published_at: string;
  url: string;
  authors: string[] | null;
}

export interface ArticleDetail extends Article {
  raw_content: string | null;
  source_meta: Record<string, unknown> | null;
  scraped_at: string;
  is_summarized: boolean;
}

export interface ArticleListResponse {
  total: number;
  articles: Article[];
}

export interface ArticleQueryParams {
  source?: string;
  tags?: string;
  limit?: string;
  offset?: string;
  since?: string;
  q?: string;
}
