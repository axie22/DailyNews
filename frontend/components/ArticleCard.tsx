import Link from "next/link";
import type { Article } from "@/types/article";
import TagBadge from "./TagBadge";
import SourceBadge from "./SourceBadge";

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

function scoreLabel(score: number): { text: string; color: string } {
  if (score >= 9) return { text: "Groundbreaking", color: "text-emerald-600 bg-emerald-50 border-emerald-200 dark:text-emerald-400 dark:bg-emerald-950 dark:border-emerald-800" };
  if (score >= 7) return { text: "Notable", color: "text-blue-600 bg-blue-50 border-blue-200 dark:text-blue-400 dark:bg-blue-950 dark:border-blue-800" };
  if (score >= 5) return { text: "Incremental", color: "text-amber-600 bg-amber-50 border-amber-200 dark:text-amber-400 dark:bg-amber-950 dark:border-amber-800" };
  return { text: "Niche", color: "text-gray-500 bg-gray-50 border-gray-200 dark:text-gray-400 dark:bg-gray-800 dark:border-gray-700" };
}

function ScoreIndicator({ score }: { score: number | null }) {
  if (score == null) return null;
  const { text, color } = scoreLabel(score);
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold border ${color}`}
      title={`Relevance: ${score}/10`}
    >
      {score}/10 &middot; {text}
    </span>
  );
}

interface ArticleCardProps {
  article: Article;
  isSeen?: boolean;
  onClickTitle?: () => void;
  compact?: boolean;
}

export default function ArticleCard({ article, isSeen, onClickTitle, compact }: ArticleCardProps) {
  const hasSummary = article.summary && article.summary.length > 0;
  const isBareUrl = article.source === "x" && /^https?:\/\/\S+$/.test(article.title.trim());

  const alsoOn: { source: string; url: string }[] =
    (article as unknown as { source_meta?: { also_on?: { source: string; url: string }[] } }).source_meta?.also_on ?? [];

  return (
    <article className={`border border-gray-200 dark:border-gray-700 rounded-xl bg-white dark:bg-gray-900 hover:border-gray-300 dark:hover:border-gray-600 hover:shadow-sm transition-all group ${isSeen ? "opacity-60" : ""}`}>
      <div className="p-4">
        {/* Row 1: metadata */}
        <div className="flex items-center gap-2 mb-2 text-[11px]">
          <SourceBadge source={article.source} />
          <span className="text-gray-300 dark:text-gray-600">&middot;</span>
          <span className="text-gray-400 dark:text-gray-500">{timeAgo(article.published_at)}</span>
          {!compact && article.authors && article.authors.length > 0 && (
            <>
              <span className="text-gray-300 dark:text-gray-600">&middot;</span>
              <span className="text-gray-400 dark:text-gray-500 truncate max-w-[200px]">
                {article.authors.slice(0, 2).join(", ")}
                {article.authors.length > 2 ? ` +${article.authors.length - 2}` : ""}
              </span>
            </>
          )}
          {alsoOn.length > 0 && (
            <>
              <span className="text-gray-300 dark:text-gray-600">&middot;</span>
              <span className="text-gray-300 dark:text-gray-600 text-[10px]">
                also on {alsoOn.map((s) => {
                  const labels: Record<string, string> = { arxiv: "arXiv", huggingface: "HF", rss: "RSS", x: "X" };
                  return labels[s.source] ?? s.source;
                }).join(" · ")}
              </span>
            </>
          )}
          <div className="ml-auto">
            <ScoreIndicator score={article.relevance_score} />
          </div>
        </div>

        {/* Row 2: title */}
        <Link href={`/article/${article.id}`} onClick={onClickTitle}>
          <h2 className={`font-semibold text-[15px] leading-snug mb-1.5 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors dark:text-gray-100 ${compact ? "line-clamp-1" : "line-clamp-2"}`}>
            {isBareUrl ? (
              <span className="text-gray-300 dark:text-gray-600 italic">Tweet (no title)</span>
            ) : (
              article.title
            )}
          </h2>
        </Link>

        {/* Row 3: key contribution chip (hidden in compact) */}
        {!compact && article.key_contribution && (
          <div className="mb-1.5">
            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-violet-700 dark:text-violet-400 bg-violet-50 dark:bg-violet-950 border border-violet-200 dark:border-violet-800 rounded-md px-2 py-0.5">
              <svg className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              {article.key_contribution}
            </span>
          </div>
        )}

        {/* Row 4: why it matters or summary */}
        {!compact && article.why_it_matters ? (
          <div className="mb-2.5">
            <p className="text-[13px] leading-relaxed line-clamp-3">
              <span className="font-semibold text-gray-700 dark:text-gray-200">{article.why_it_matters}</span>
              {hasSummary && (
                <span className="text-gray-400 dark:text-gray-500"> — {article.summary}</span>
              )}
            </p>
          </div>
        ) : hasSummary ? (
          <p className={`text-[13px] text-gray-500 dark:text-gray-400 leading-relaxed mb-2.5 ${compact ? "line-clamp-1" : "line-clamp-2"}`}>
            {article.summary}
          </p>
        ) : (
          <p className="text-[13px] text-gray-300 dark:text-gray-600 italic mb-2.5">
            Summary pending...
          </p>
        )}

        {/* Row 5: tags + link */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex gap-1 flex-wrap min-w-0">
            {article.tags && article.tags.length > 0 ? (
              article.tags.slice(0, compact ? 2 : 4).map((tag) => <TagBadge key={tag} tag={tag} />)
            ) : (
              <span className="text-[11px] text-gray-300 dark:text-gray-600">--</span>
            )}
          </div>
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[11px] text-gray-400 hover:text-blue-500 dark:text-gray-500 dark:hover:text-blue-400 transition-colors whitespace-nowrap flex items-center gap-0.5 shrink-0"
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
