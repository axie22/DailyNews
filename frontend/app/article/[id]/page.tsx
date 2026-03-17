import Link from "next/link";
import { getArticle } from "@/lib/api";
import TagBadge from "@/components/TagBadge";

const SOURCE_LABELS: Record<string, string> = {
  arxiv: "arXiv",
  huggingface: "Hugging Face",
  rss: "RSS",
  x: "X (Twitter)",
};

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString("en-US", {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function ScoreBadge({ score }: { score: number | null }) {
  if (score == null) return null;
  const color =
    score >= 8 ? "bg-emerald-100 text-emerald-700 border-emerald-200" :
    score >= 6 ? "bg-blue-100 text-blue-700 border-blue-200" :
    score >= 4 ? "bg-amber-100 text-amber-700 border-amber-200" :
    "bg-gray-100 text-gray-500 border-gray-200";
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-semibold border ${color}`}>
      <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
      </svg>
      {score}/10
    </span>
  );
}

export default async function ArticlePage({ params }: { params: { id: string } }) {
  let article;
  try {
    article = await getArticle(params.id);
  } catch {
    return (
      <div className="text-center py-16 text-gray-500">
        <div className="text-gray-300 text-4xl mb-3">?</div>
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
        className="text-xs text-gray-400 hover:text-gray-600 mb-5 inline-flex items-center gap-1 transition-colors"
      >
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Back to feed
      </Link>

      <article className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
        {/* Header */}
        <div className="px-6 pt-6 pb-4">
          <div className="flex items-center gap-2 mb-3 text-xs">
            <span className="font-semibold text-gray-600">
              {SOURCE_LABELS[article.source] ?? article.source}
            </span>
            <span className="text-gray-300">&middot;</span>
            <span className="text-gray-400">{formatDate(article.published_at)}</span>
            <div className="ml-auto">
              <ScoreBadge score={article.relevance_score} />
            </div>
          </div>

          <h1 className="text-xl font-bold leading-snug tracking-tight mb-3">
            {article.title}
          </h1>

          {article.authors && article.authors.length > 0 && (
            <p className="text-sm text-gray-500 mb-3">
              {article.authors.join(", ")}
            </p>
          )}

          {/* X/Twitter engagement metrics */}
          {article.source === "x" && meta && (
            <div className="flex items-center gap-4 text-xs text-gray-500 py-2.5 px-3.5 bg-gray-50 rounded-lg border border-gray-100">
              {meta.author && (
                <span className="font-medium text-gray-700">@{String(meta.author)}</span>
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

        {/* Summary */}
        {article.summary ? (
          <div className="mx-6 mb-4 bg-blue-50/70 border border-blue-100 rounded-lg p-4">
            <div className="text-[10px] font-semibold text-blue-400 uppercase tracking-wider mb-1.5">
              TL;DR
            </div>
            <p className="text-[14px] text-gray-700 leading-relaxed">{article.summary}</p>
          </div>
        ) : (
          <div className="mx-6 mb-4 bg-gray-50 border border-gray-100 rounded-lg p-4">
            <p className="text-sm text-gray-400 italic">Summary is being generated...</p>
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
        <div className="border-t border-gray-100 mx-6" />

        {/* Raw content */}
        {article.raw_content && (
          <div className="p-6">
            <div className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-3">
              {article.source === "x" ? "Full Tweet" : "Abstract / Excerpt"}
            </div>
            <div className="text-[14px] text-gray-600 leading-[1.7] whitespace-pre-line">
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
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-gray-900 text-white rounded-lg text-sm font-medium hover:bg-gray-700 transition-colors"
          >
            Read original
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </a>

          {!article.is_summarized && (
            <span className="text-[11px] text-gray-400">
              Summary pending &mdash; generated periodically.
            </span>
          )}
        </div>
      </article>
    </div>
  );
}
