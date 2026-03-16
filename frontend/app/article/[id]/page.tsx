import Link from "next/link";
import { getArticle } from "@/lib/api";
import TagBadge from "@/components/TagBadge";

const SOURCE_LABELS: Record<string, string> = {
  arxiv: "arXiv",
  huggingface: "Hugging Face",
  rss: "RSS",
  x: "X (Twitter)",
};

export default async function ArticlePage({ params }: { params: { id: string } }) {
  let article;
  try {
    article = await getArticle(params.id);
  } catch {
    return (
      <div className="text-center py-12 text-gray-500">
        Article not found. <Link href="/" className="text-blue-500 underline">Go back</Link>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      <Link href="/" className="text-sm text-gray-400 hover:text-gray-600 mb-4 inline-block">
        ← Back to feed
      </Link>
      <div className="bg-white border rounded-xl p-6">
        <div className="flex items-center gap-2 mb-3 text-sm text-gray-500">
          <span className="font-medium">{SOURCE_LABELS[article.source] ?? article.source}</span>
          <span>·</span>
          <span>{new Date(article.published_at).toLocaleDateString()}</span>
          {article.authors && article.authors.length > 0 && (
            <>
              <span>·</span>
              <span>{article.authors.join(", ")}</span>
            </>
          )}
        </div>
        <h1 className="text-xl font-bold mb-4 leading-snug">{article.title}</h1>
        {article.summary && (
          <div className="bg-gray-50 rounded-lg p-4 mb-4">
            <div className="text-xs font-semibold text-gray-400 uppercase mb-1">Summary</div>
            <p className="text-sm text-gray-700">{article.summary}</p>
          </div>
        )}
        {article.tags && article.tags.length > 0 && (
          <div className="flex gap-1.5 flex-wrap mb-4">
            {article.tags.map((tag) => <TagBadge key={tag} tag={tag} />)}
          </div>
        )}
        {article.raw_content && (
          <div className="mb-4">
            <div className="text-xs font-semibold text-gray-400 uppercase mb-1">Abstract / Excerpt</div>
            <p className="text-sm text-gray-600 leading-relaxed">{article.raw_content}</p>
          </div>
        )}
        <a
          href={article.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-block mt-2 px-4 py-2 bg-gray-900 text-white rounded-lg text-sm hover:bg-gray-700 transition-colors"
        >
          Read original →
        </a>
      </div>
    </div>
  );
}
