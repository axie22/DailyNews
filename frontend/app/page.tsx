"use client";

import { useState, useEffect, useCallback } from "react";
import ArticleCard from "@/components/ArticleCard";
import FilterBar from "@/components/FilterBar";
import { getArticles, getTags } from "@/lib/api";
import type { Article } from "@/types/article";

export default function FeedPage() {
  const [articles, setArticles] = useState<Article[]>([]);
  const [total, setTotal] = useState(0);
  const [source, setSource] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [availableTags, setAvailableTags] = useState<[string, number][]>([]);
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const LIMIT = 20;

  const fetchArticles = useCallback(async (reset = false) => {
    setLoading(true);
    try {
      const currentOffset = reset ? 0 : offset;
      const data = await getArticles({
        source: source || undefined,
        tags: selectedTags.length ? selectedTags.join(",") : undefined,
        q: search || undefined,
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
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [source, selectedTags, search, offset]);

  useEffect(() => {
    setOffset(0);
    fetchArticles(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, selectedTags, search]);

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

  return (
    <div>
      <FilterBar
        source={source}
        selectedTags={selectedTags}
        availableTags={availableTags}
        search={search}
        onSourceChange={setSource}
        onTagToggle={toggleTag}
        onSearchChange={setSearch}
      />
      <div className="text-xs text-gray-400 mb-4">{total} articles</div>
      <div className="grid gap-4 sm:grid-cols-2">
        {articles.map((a) => (
          <ArticleCard key={a.id} article={a} />
        ))}
      </div>
      {articles.length < total && (
        <div className="flex justify-center mt-6">
          <button
            onClick={() => fetchArticles(false)}
            disabled={loading}
            className="px-6 py-2 bg-gray-900 text-white rounded-full text-sm hover:bg-gray-700 disabled:opacity-50"
          >
            {loading ? "Loading..." : "Load more"}
          </button>
        </div>
      )}
      {loading && articles.length === 0 && (
        <div className="text-center text-gray-400 py-12">Loading...</div>
      )}
    </div>
  );
}
