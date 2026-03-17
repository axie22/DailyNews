import Link from "next/link";
import type { Article } from "@/types/article";
import TagBadge from "./TagBadge";
import SourceBadge from "./SourceBadge";

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const hrs = Math.floor(diff / 3600000);
  if (hrs < 1) return "just now";
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return "yesterday";
  return `${days}d ago`;
}

export default function DigestCard({ article, rank }: { article: Article; rank: number }) {
  return (
    <li className="flex gap-4">
      <span className="text-3xl font-black text-gray-100 dark:text-gray-800 w-8 shrink-0 mt-0.5 select-none tabular-nums">
        {rank}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 text-[11px] mb-1">
          <SourceBadge source={article.source} />
          <span className="text-gray-400 dark:text-gray-500">{timeAgo(article.published_at)}</span>
          {article.relevance_score != null && (
            <span className="text-gray-300 dark:text-gray-600 tabular-nums">{article.relevance_score}/10</span>
          )}
        </div>
        <Link href={`/article/${article.id}`}>
          <h2 className="font-bold text-base leading-snug mb-1.5 hover:text-blue-600 dark:hover:text-blue-400 transition-colors dark:text-gray-100">
            {article.title}
          </h2>
        </Link>
        {article.key_contribution && (
          <div className="mb-1.5">
            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-violet-700 dark:text-violet-400 bg-violet-50 dark:bg-violet-950 border border-violet-200 dark:border-violet-800 rounded-md px-2 py-0.5">
              <svg className="w-3 h-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              {article.key_contribution}
            </span>
          </div>
        )}
        {article.why_it_matters && (
          <p className="text-[13px] font-semibold text-gray-800 dark:text-gray-200 mb-1">
            {article.why_it_matters}
          </p>
        )}
        {article.summary && (
          <p className="text-[13px] text-gray-500 dark:text-gray-400 leading-relaxed">
            {article.summary}
          </p>
        )}
        <div className="flex items-center gap-2 mt-2">
          {article.tags?.slice(0, 3).map((t) => (
            <TagBadge key={t} tag={t} />
          ))}
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto text-[11px] text-gray-400 hover:text-blue-500 dark:text-gray-500 dark:hover:text-blue-400 transition-colors flex items-center gap-0.5"
          >
            Read original
            <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </a>
        </div>
      </div>
    </li>
  );
}
