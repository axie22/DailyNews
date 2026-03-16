import Link from "next/link";
import type { Article } from "@/types/article";
import TagBadge from "./TagBadge";

const SOURCE_BADGES: Record<string, { label: string; color: string }> = {
  arxiv: { label: "arXiv", color: "bg-red-100 text-red-700" },
  huggingface: { label: "HF", color: "bg-yellow-100 text-yellow-700" },
  rss: { label: "RSS", color: "bg-blue-100 text-blue-700" },
  x: { label: "X", color: "bg-gray-100 text-gray-700" },
};

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function ArticleCard({ article }: { article: Article }) {
  const badge = SOURCE_BADGES[article.source] ?? { label: article.source, color: "bg-gray-100 text-gray-600" };

  return (
    <article className="border rounded-lg p-4 bg-white hover:shadow-md transition-shadow">
      <div className="flex items-center gap-2 mb-2">
        <span className={`px-2 py-0.5 rounded text-xs font-semibold ${badge.color}`}>{badge.label}</span>
        <span className="text-xs text-gray-400">{timeAgo(article.published_at)}</span>
        {article.authors && article.authors.length > 0 && (
          <span className="text-xs text-gray-400 truncate max-w-xs">
            {article.authors.slice(0, 2).join(", ")}
            {article.authors.length > 2 ? " et al." : ""}
          </span>
        )}
      </div>
      <Link href={`/article/${article.id}`}>
        <h2 className="font-semibold text-sm mb-1 hover:text-blue-600 transition-colors line-clamp-2">
          {article.title}
        </h2>
      </Link>
      {article.summary && (
        <p className="text-sm text-gray-600 line-clamp-3 mb-2">{article.summary}</p>
      )}
      <div className="flex items-center justify-between mt-2">
        <div className="flex gap-1 flex-wrap">
          {article.tags?.map((tag) => <TagBadge key={tag} tag={tag} />)}
        </div>
        <a
          href={article.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-blue-500 hover:underline whitespace-nowrap ml-2"
        >
          Read original →
        </a>
      </div>
    </article>
  );
}
