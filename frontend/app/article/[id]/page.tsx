import Link from "next/link";
import { getArticle, getRelated } from "@/lib/api";
import TagBadge from "@/components/TagBadge";
import SourceBadge from "@/components/SourceBadge";
import ArticleCard from "@/components/ArticleCard";

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString("en-US", {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function scoreLabel(score: number): { text: string; color: string } {
  if (score >= 9) return { text: "Groundbreaking", color: "text-emerald-700 bg-emerald-50 border-emerald-200 dark:text-emerald-400 dark:bg-emerald-950 dark:border-emerald-800" };
  if (score >= 7) return { text: "Notable", color: "text-blue-700 bg-blue-50 border-blue-200 dark:text-blue-400 dark:bg-blue-950 dark:border-blue-800" };
  if (score >= 5) return { text: "Incremental", color: "text-amber-700 bg-amber-50 border-amber-200 dark:text-amber-400 dark:bg-amber-950 dark:border-amber-800" };
  return { text: "Niche", color: "text-gray-500 bg-gray-50 border-gray-200 dark:text-gray-400 dark:bg-gray-800 dark:border-gray-700" };
}

function ScoreBadge({ score }: { score: number | null }) {
  if (score == null) return null;
  const { text, color } = scoreLabel(score);
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold border ${color}`}>
      <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
      </svg>
      {score}/10 &middot; {text}
    </span>
  );
}

export default async function ArticlePage({ params }: { params: { id: string } }) {
  let article;
  let related;
  try {
    [article, { articles: related }] = await Promise.all([
      getArticle(params.id),
      getRelated(params.id),
    ]);
  } catch {
    return (
      <div className="text-center py-16 text-gray-500 dark:text-gray-400">
        <div className="text-gray-300 dark:text-gray-600 text-4xl mb-3">?</div>
        <p className="text-sm mb-2">Article not found.</p>
        <Link href="/" className="text-sm text-blue-500 hover:underline">
          Back to feed
        </Link>
      </div>
    );
  }

  const meta = article.source_meta as Record<string, unknown> | null;

  return (
    <div className="max-w-2xl mx-auto">
      <Link
        href="/"
        className="text-xs text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 mb-5 inline-flex items-center gap-1 transition-colors"
      >
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Back to feed
      </Link>

      <article className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden shadow-sm">
        {/* Header */}
        <div className="px-6 pt-6 pb-4">
          <div className="flex items-center gap-2 mb-3 text-xs">
            <SourceBadge source={article.source} />
            <span className="text-gray-300 dark:text-gray-600">&middot;</span>
            <span className="text-gray-400 dark:text-gray-500">{formatDate(article.published_at)}</span>
            <div className="ml-auto">
              <ScoreBadge score={article.relevance_score} />
            </div>
          </div>

          <h1 className="text-xl font-bold leading-snug tracking-tight mb-3 dark:text-gray-100">
            {article.title}
          </h1>

          {article.authors && article.authors.length > 0 && (
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">
              {article.authors.join(", ")}
            </p>
          )}

          {/* X/Twitter engagement metrics */}
          {article.source === "x" && meta && (
            <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400 py-2.5 px-3.5 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-100 dark:border-gray-700">
              {meta.author && (
                <span className="font-medium text-gray-700 dark:text-gray-200">@{String(meta.author)}</span>
              )}
              {typeof meta.likes === "number" && (
                <span className="flex items-center gap-1">
                  <svg className="w-3.5 h-3.5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M3.172 5.172a4 4 0 015.656 0L10 6.343l1.172-1.171a4 4 0 115.656 5.656L10 17.657l-6.828-6.829a4 4 0 010-5.656z" />
                  </svg>
                  {meta.likes.toLocaleString()}
                </span>
              )}
              {typeof meta.retweets === "number" && (
                <span className="flex items-center gap-1">
                  <svg className="w-3.5 h-3.5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  {meta.retweets.toLocaleString()}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Key contribution + Why it matters */}
        {(article.key_contribution || article.why_it_matters) && (
          <div className="mx-6 mb-3 flex flex-col gap-2">
            {article.key_contribution && (
              <span className="inline-flex items-center gap-1.5 self-start text-xs font-medium text-violet-700 dark:text-violet-400 bg-violet-50 dark:bg-violet-950 border border-violet-200 dark:border-violet-800 rounded-md px-2.5 py-1">
                <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                {article.key_contribution}
              </span>
            )}
            {article.why_it_matters && (
              <p className="text-sm font-medium text-gray-700 dark:text-gray-200">
                {article.why_it_matters}
              </p>
            )}
          </div>
        )}

        {/* Summary */}
        {article.summary ? (
          <div className="mx-6 mb-4 bg-blue-50/70 dark:bg-blue-950 border border-blue-100 dark:border-blue-800 rounded-lg p-4">
            <div className="text-[10px] font-semibold text-blue-400 dark:text-blue-500 uppercase tracking-wider mb-1.5">
              TL;DR
            </div>
            <p className="text-[14px] text-gray-700 dark:text-gray-200 leading-relaxed">{article.summary}</p>
          </div>
        ) : (
          <div className="mx-6 mb-4 bg-gray-50 dark:bg-gray-800 border border-gray-100 dark:border-gray-700 rounded-lg p-4">
            <p className="text-sm text-gray-400 dark:text-gray-500 italic">Summary is being generated...</p>
          </div>
        )}

        {/* Tags */}
        {article.tags && article.tags.length > 0 && (
          <div className="px-6 mb-4 flex gap-1.5 flex-wrap">
            {article.tags.map((tag) => (
              <TagBadge key={tag} tag={tag} />
            ))}
          </div>
        )}

        {/* Divider */}
        <div className="border-t border-gray-100 dark:border-gray-800 mx-6" />

        {/* Raw content */}
        {article.raw_content && (
          <div className="p-6">
            <div className="text-[10px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-3">
              {article.source === "x" ? "Full Tweet" : "Abstract / Excerpt"}
            </div>
            <div className="text-[14px] text-gray-600 dark:text-gray-300 leading-[1.7] whitespace-pre-line">
              {article.raw_content}
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="px-6 pb-6 flex items-center gap-3">
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 rounded-lg text-sm font-medium hover:bg-gray-700 dark:hover:bg-gray-300 transition-colors"
          >
            Read original
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </a>

          {!article.is_summarized && (
            <span className="text-[11px] text-gray-400 dark:text-gray-500">
              Summary pending &mdash; generated periodically.
            </span>
          )}
        </div>
      </article>

      {/* Related articles */}
      {related.length > 0 && (
        <div className="mt-8">
          <h2 className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-widest mb-4">
            Related
          </h2>
          <div className="space-y-2">
            {related.map((r) => (
              <ArticleCard key={r.id} article={r} compact />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
