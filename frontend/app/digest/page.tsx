import Link from "next/link";
import { getArticles } from "@/lib/api";
import DigestCard from "@/components/DigestCard";

export default async function DigestPage() {
  const { articles } = await getArticles({ digest: "true", limit: "10" });
  const today = new Date().toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-8">
        <p className="text-xs text-gray-400 dark:text-gray-500 uppercase tracking-widest mb-1">
          Daily Digest
        </p>
        <h1 className="text-2xl font-bold tracking-tight dark:text-gray-100">{today}</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          {articles.length > 0
            ? `Top ${articles.length} ${articles.length === 1 ? "story" : "stories"} from the past 24 hours`
            : "No stories from the past 24 hours yet"}
        </p>
      </div>

      {articles.length > 0 ? (
        <ol className="space-y-6">
          {articles.map((article, i) => (
            <DigestCard key={article.id} article={article} rank={i + 1} />
          ))}
        </ol>
      ) : (
        <div className="text-center py-16">
          <div className="text-gray-300 dark:text-gray-600 text-4xl mb-3">--</div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">
            No articles have been processed in the last 24 hours.
          </p>
          <Link href="/" className="text-sm text-blue-500 hover:underline">
            Back to feed
          </Link>
        </div>
      )}
    </div>
  );
}
