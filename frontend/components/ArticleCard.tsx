import Link from "next/link";
import type { Article } from "@/types/article";
import TagBadge from "./TagBadge";

const SOURCE_BADGES: Record<string, { label: string; color: string }> = {
  arxiv: { label: "arXiv", color: "bg-red-50 text-red-600 border-red-200" },
  huggingface: { label: "HF Papers", color: "bg-amber-50 text-amber-600 border-amber-200" },
  rss: { label: "RSS", color: "bg-blue-50 text-blue-600 border-blue-200" },
  x: { label: "X", color: "bg-gray-50 text-gray-600 border-gray-200" },
};

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export default function ArticleCard({ article }: { article: Article }) {
  const badge = SOURCE_BADGES[article.source] ?? {
    label: article.source,
    color: "bg-gray-50 text-gray-600 border-gray-200",
  };
  const hasSummary = article.summary && article.summary.length > 0;

  return (
    <article className="border border-gray-200 rounded-xl p-4 bg-white hover:shadow-md hover:border-gray-300 transition-all group">
      {/* Header: source, time, authors */}
      <div className="flex items-center gap-2 mb-2 text-xs">
        <span className={`px-2 py-0.5 rounded-md border font-semibold ${badge.color}`}>
          {badge.label}
        </span>
        <span className="text-gray-400">{timeAgo(article.published_at)}</span>
        {article.authors && article.authors.length > 0 && (
          <>
            <span className="text-gray-300">|</span>
            <span className="text-gray-400 truncate">
              {article.authors.slice(0, 2).join(", ")}
              {article.authors.length > 2 ? ` +${article.authors.length - 2}` : ""}
            </span>
          </>
        )}
      </div>

      {/* Title */}
      <Link href={`/article/${article.id}`}>
        <h2 className="font-semibold text-[15px] leading-snug mb-1.5 group-hover:text-blue-600 transition-colors line-clamp-2">
          {article.title}
        </h2>
      </Link>

      {/* Summary or placeholder */}
      {hasSummary ? (
        <p className="text-sm text-gray-600 leading-relaxed line-clamp-3 mb-2.5">
          {article.summary}
        </p>
      ) : (
        <p className="text-sm text-gray-400 italic mb-2.5">
          Summary pending...
        </p>
      )}

      {/* Footer: tags + external link */}
      <div className="flex items-center justify-between">
        <div className="flex gap-1 flex-wrap">
          {article.tags && article.tags.length > 0 ? (
            article.tags.map((tag) => <TagBadge key={tag} tag={tag} />)
          ) : (
            <span className="text-[11px] text-gray-300">No tags yet</span>
          )}
        </div>
        <a
          href={article.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-gray-400 hover:text-blue-500 transition-colors whitespace-nowrap ml-3 flex items-center gap-1"
        >
          Original
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
          </svg>
        </a>
      </div>
    </article>
  );
}
