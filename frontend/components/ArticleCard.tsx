import Link from "next/link";
import type { Article } from "@/types/article";
import TagBadge from "./TagBadge";

const SOURCE_LABELS: Record<string, string> = {
  arxiv: "arXiv",
  huggingface: "HF Papers",
  rss: "RSS",
  x: "X",
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

function ScoreBar({ score }: { score: number | null }) {
  if (score == null) return null;
  const width = score * 10;
  const color =
    score >= 8 ? "bg-emerald-500" :
    score >= 6 ? "bg-blue-500" :
    score >= 4 ? "bg-amber-400" : "bg-gray-300";
  return (
    <div className="flex items-center gap-1.5" title={`Relevance: ${score}/10`}>
      <div className="w-12 h-1 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${width}%` }} />
      </div>
      <span className="text-[10px] text-gray-400 tabular-nums">{score}</span>
    </div>
  );
}

export default function ArticleCard({ article }: { article: Article }) {
  const hasSummary = article.summary && article.summary.length > 0;

  return (
    <article className="border border-gray-200 rounded-xl bg-white hover:border-gray-300 hover:shadow-sm transition-all group">
      <div className="p-4">
        {/* Row 1: metadata */}
        <div className="flex items-center gap-2 mb-2 text-[11px]">
          <span className="font-semibold text-gray-500">
            {SOURCE_LABELS[article.source] ?? article.source}
          </span>
          <span className="text-gray-300">&middot;</span>
          <span className="text-gray-400">{timeAgo(article.published_at)}</span>
          {article.authors && article.authors.length > 0 && (
            <>
              <span className="text-gray-300">&middot;</span>
              <span className="text-gray-400 truncate max-w-[200px]">
                {article.authors.slice(0, 2).join(", ")}
                {article.authors.length > 2 ? ` +${article.authors.length - 2}` : ""}
              </span>
            </>
          )}
          <div className="ml-auto">
            <ScoreBar score={article.relevance_score} />
          </div>
        </div>

        {/* Row 2: title */}
        <Link href={`/article/${article.id}`}>
          <h2 className="font-semibold text-[15px] leading-snug mb-1 group-hover:text-blue-600 transition-colors line-clamp-2">
            {article.title}
          </h2>
        </Link>

        {/* Row 3: summary */}
        {hasSummary ? (
          <p className="text-[13px] text-gray-500 leading-relaxed line-clamp-2 mb-2.5">
            {article.summary}
          </p>
        ) : (
          <p className="text-[13px] text-gray-300 italic mb-2.5">
            Summary pending...
          </p>
        )}

        {/* Row 4: tags + link */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex gap-1 flex-wrap min-w-0">
            {article.tags && article.tags.length > 0 ? (
              article.tags.slice(0, 4).map((tag) => <TagBadge key={tag} tag={tag} />)
            ) : (
              <span className="text-[11px] text-gray-300">--</span>
            )}
          </div>
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[11px] text-gray-400 hover:text-blue-500 transition-colors whitespace-nowrap flex items-center gap-0.5 shrink-0"
          >
            Source
            <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </a>
        </div>
      </div>
    </article>
  );
}
