import Link from "next/link";
import type { Article } from "@/types/article";
import SourceBadge from "./SourceBadge";

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const hrs = Math.floor(diff / 3600000);
  if (hrs < 1) return "just now";
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function ScoreDot({ score }: { score: number | null }) {
  if (score == null) return null;
  const color =
    score >= 9 ? "bg-emerald-500" :
    score >= 7 ? "bg-blue-500" :
    score >= 5 ? "bg-amber-500" : "bg-gray-400";
  return (
    <span className={`inline-block w-2 h-2 rounded-full ${color}`} title={`Score: ${score}/10`} />
  );
}

export default function TopPicks({ articles }: { articles: Article[] }) {
  if (articles.length === 0) return null;

  return (
    <section className="mb-8">
      <div className="flex items-center gap-2 mb-3">
        <svg className="w-4 h-4 text-amber-500" fill="currentColor" viewBox="0 0 20 20">
          <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
        </svg>
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100 tracking-tight">Top Picks</h2>
        <span className="text-xs text-gray-400 dark:text-gray-500">Highest rated this week</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        {articles.slice(0, 6).map((a, i) => (
          <Link
            key={a.id}
            href={`/article/${a.id}`}
            className={`group block rounded-xl border p-3.5 transition-all hover:shadow-md ${
              i === 0
                ? "sm:col-span-2 bg-gradient-to-br from-amber-50 to-orange-50 dark:from-amber-950 dark:to-orange-950 border-amber-200 dark:border-amber-800 hover:border-amber-300 dark:hover:border-amber-700"
                : "bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"
            }`}
          >
            <div className="flex items-center gap-2 mb-1.5">
              <ScoreDot score={a.relevance_score} />
              <SourceBadge source={a.source} />
              <span className="text-[11px] text-gray-300 dark:text-gray-600">{timeAgo(a.published_at)}</span>
            </div>
            <h3 className={`font-semibold leading-snug group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors dark:text-gray-100 line-clamp-2 ${
              i === 0 ? "text-[15px]" : "text-sm"
            }`}>
              {a.title}
            </h3>
            {a.summary && (
              <p className={`text-gray-500 dark:text-gray-400 leading-relaxed mt-1 ${
                i === 0 ? "text-sm line-clamp-2" : "text-xs line-clamp-1"
              }`}>
                {a.summary}
              </p>
            )}
          </Link>
        ))}
      </div>
    </section>
  );
}
