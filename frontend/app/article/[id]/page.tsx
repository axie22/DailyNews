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
        className="text-xs text-gray-400 hover:text-gray-600 mb-4 inline-flex items-center gap-1 transition-colors"
      >
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Back to feed
      </Link>

      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        {/* Header section */}
        <div className="p-6 pb-0">
          <div className="flex items-center gap-2 mb-3 text-xs text-gray-500">
            <span className="font-semibold text-gray-700">
              {SOURCE_LABELS[article.source] ?? article.source}
            </span>
            <span className="text-gray-300">|</span>
            <span>{formatDate(article.published_at)}</span>
            {article.authors && article.authors.length > 0 && (
              <>
                <span className="text-gray-300">|</span>
                <span className="truncate">{article.authors.join(", ")}</span>
              </>
            )}
          </div>

          <h1 className="text-xl font-bold mb-4 leading-snug">{article.title}</h1>

          {/* X/Twitter engagement metrics */}
          {article.source === "x" && meta && (
            <div className="flex items-center gap-4 text-xs text-gray-500 mb-4 py-2 px-3 bg-gray-50 rounded-lg">
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
          <div className="mx-6 mb-4 bg-blue-50 border border-blue-100 rounded-lg p-4">
            <div className="text-[10px] font-semibold text-blue-400 uppercase tracking-wider mb-1.5">
              TL;DR
            </div>
            <p className="text-sm text-gray-700 leading-relaxed">{article.summary}</p>
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
            <div className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2">
              {article.source === "x" ? "Full Tweet" : "Abstract / Excerpt"}
            </div>
            <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-line">
              {article.raw_content}
            </p>
          </div>
        )}

        {/* Footer action */}
        <div className="px-6 pb-6">
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
            <p className="text-[11px] text-gray-400 mt-3">
              This article hasn&apos;t been summarized yet. Summaries are generated periodically.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
