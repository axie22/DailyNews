"use client";

import TagBadge from "./TagBadge";

const SOURCES = [
  { value: "", label: "All" },
  { value: "arxiv", label: "arXiv" },
  { value: "huggingface", label: "HF Papers" },
  { value: "rss", label: "RSS" },
  { value: "x", label: "X" },
];

interface FilterBarProps {
  source: string;
  selectedTags: string[];
  availableTags: [string, number][];
  search: string;
  recommended: boolean;
  onSourceChange: (s: string) => void;
  onTagToggle: (tag: string) => void;
  onSearchChange: (q: string) => void;
  onRecommendedToggle: () => void;
  onClearFilters: () => void;
  hasFilters: boolean;
}

export default function FilterBar({
  source,
  selectedTags,
  availableTags,
  search,
  recommended,
  onSourceChange,
  onTagToggle,
  onSearchChange,
  onRecommendedToggle,
  onClearFilters,
  hasFilters,
}: FilterBarProps) {
  return (
    <div className="mb-5 space-y-2.5">
      {/* Search */}
      <div className="relative">
        <svg
          className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          type="text"
          placeholder="Search articles..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="w-full pl-9 pr-3 py-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-gray-300 placeholder:text-gray-400 transition-all"
        />
      </div>

      {/* Source filters + recommended toggle */}
      <div className="flex items-center gap-1.5 flex-wrap">
        {SOURCES.map((s) => (
          <button
            key={s.value}
            onClick={() => onSourceChange(s.value)}
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
              source === s.value && !recommended
                ? "bg-gray-900 text-white"
                : "text-gray-500 hover:bg-gray-100"
            }`}
          >
            {s.label}
          </button>
        ))}

        <div className="w-px h-4 bg-gray-200 mx-1" />

        <button
          onClick={onRecommendedToggle}
          className={`px-3 py-1 rounded-lg text-xs font-medium transition-all flex items-center gap-1 ${
            recommended
              ? "bg-amber-500 text-white"
              : "text-gray-500 hover:bg-amber-50"
          }`}
        >
          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
            <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
          </svg>
          Top Picks
        </button>

        {hasFilters && (
          <button
            onClick={onClearFilters}
            className="px-2 py-1 text-xs text-gray-400 hover:text-gray-600 transition-colors"
          >
            Clear
          </button>
        )}
      </div>

      {/* Tags */}
      {availableTags.length > 0 && (
        <div className="flex gap-1.5 flex-wrap items-center">
          {availableTags.slice(0, 12).map(([tag, count]) => (
            <button
              key={tag}
              onClick={() => onTagToggle(tag)}
              className={`transition-all ${
                selectedTags.includes(tag)
                  ? "ring-2 ring-gray-900 ring-offset-1 rounded"
                  : "opacity-60 hover:opacity-100"
              }`}
            >
              <TagBadge tag={tag} count={count} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
