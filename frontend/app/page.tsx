"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import ArticleCard from "@/components/ArticleCard";
import FilterBar from "@/components/FilterBar";
import SkeletonCard from "@/components/SkeletonCard";
import { getArticles, getTags } from "@/lib/api";
import type { Article } from "@/types/article";

export default function FeedPage() {
  const [articles, setArticles] = useState<Article[]>([]);
  const [total, setTotal] = useState(0);
  const [source, setSource] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [availableTags, setAvailableTags] = useState<[string, number][]>([]);
  const [search, setSearch] = useState("");
  const [recommended, setRecommended] = useState(false);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const LIMIT = 20;

  // Debounce search input
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const searchTimer = useRef<NodeJS.Timeout>();
  const handleSearchChange = (q: string) => {
    setSearch(q);
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => setDebouncedSearch(q), 300);
  };

  const fetchArticles = useCallback(async (reset = false) => {
    if (reset) setLoading(true);
    else setLoadingMore(true);
    setError(null);
    try {
      const currentOffset = reset ? 0 : offset;
      const data = await getArticles({
        source: source || undefined,
        tags: selectedTags.length ? selectedTags.join(",") : undefined,
        q: debouncedSearch || undefined,
        recommended: recommended ? "true" : undefined,
        limit: String(LIMIT),
        offset: String(currentOffset),
      });
      if (reset) {
        setArticles(data.articles);
        setOffset(data.articles.length);
      } else {
        setArticles((prev) => [...prev, ...data.articles]);
        setOffset((prev) => prev + data.articles.length);
      }
      setTotal(data.total);
    } catch (e) {
      setError("Failed to load articles. Is the backend running?");
      console.error(e);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [source, selectedTags, debouncedSearch, recommended, offset]);

  useEffect(() => {
    setOffset(0);
    fetchArticles(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, selectedTags, debouncedSearch, recommended]);

  useEffect(() => {
    getTags().then(setAvailableTags).catch(console.error);
    const interval = setInterval(() => fetchArticles(true), 10 * 60 * 1000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  };

  const clearFilters = () => {
    setSource("");
    setSelectedTags([]);
    setSearch("");
    setDebouncedSearch("");
    setRecommended(false);
  };

  const hasFilters = source !== "" || selectedTags.length > 0 || search !== "" || recommended;

  return (
    <div>
      <FilterBar
        source={source}
        selectedTags={selectedTags}
        availableTags={availableTags}
        search={search}
        recommended={recommended}
        onSourceChange={setSource}
        onTagToggle={toggleTag}
        onSearchChange={handleSearchChange}
        onRecommendedToggle={() => setRecommended((prev) => !prev)}
        onClearFilters={clearFilters}
        hasFilters={hasFilters}
      />

      {/* Results count */}
      {!loading && !error && (
        <div className="flex items-center justify-between mb-4">
          <span className="text-xs text-gray-400">
            {total} article{total !== 1 ? "s" : ""}
            {hasFilters ? " matching filters" : ""}
          </span>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="text-center py-16">
          <div className="text-gray-300 text-4xl mb-3">!</div>
          <p className="text-sm text-gray-500 mb-3">{error}</p>
          <button
            onClick={() => fetchArticles(true)}
            className="px-4 py-1.5 bg-gray-900 text-white rounded-full text-sm hover:bg-gray-700"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading skeletons */}
      {loading && !error && (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      )}

      {/* Articles list — single column for scannability */}
      {!loading && !error && articles.length > 0 && (
        <div className="space-y-3">
          {articles.map((a) => (
            <ArticleCard key={a.id} article={a} />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && articles.length === 0 && (
        <div className="text-center py-16">
          <div className="text-gray-300 text-4xl mb-3">
            {hasFilters ? "0" : "--"}
          </div>
          <p className="text-sm text-gray-500 mb-1">
            {recommended
              ? "No recommended articles yet. Recommendations are generated after summarization."
              : hasFilters
              ? "No articles match your filters."
              : "No articles yet. The pipeline may still be running."}
          </p>
          {hasFilters && (
            <button
              onClick={clearFilters}
              className="text-sm text-blue-500 hover:underline mt-2"
            >
              Clear all filters
            </button>
          )}
        </div>
      )}

      {/* Load more */}
      {!loading && !error && articles.length < total && (
        <div className="flex justify-center mt-8 mb-4">
          <button
            onClick={() => fetchArticles(false)}
            disabled={loadingMore}
            className="px-6 py-2 bg-gray-900 text-white rounded-full text-sm hover:bg-gray-700 disabled:opacity-50 transition-colors"
          >
            {loadingMore ? (
              <span className="flex items-center gap-2">
                <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Loading...
              </span>
            ) : (
              `Load more (${articles.length} of ${total})`
            )}
          </button>
        </div>
      )}
    </div>
  );
}
