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
  onSourceChange: (s: string) => void;
  onTagToggle: (tag: string) => void;
  onSearchChange: (q: string) => void;
  onClearFilters: () => void;
  hasFilters: boolean;
}

export default function FilterBar({
  source,
  selectedTags,
  availableTags,
  search,
  onSourceChange,
  onTagToggle,
  onSearchChange,
  onClearFilters,
  hasFilters,
}: FilterBarProps) {
  return (
    <div className="mb-6 space-y-3">
      {/* Source filters + search */}
      <div className="flex items-center gap-2 flex-wrap">
        {SOURCES.map((s) => (
          <button
            key={s.value}
            onClick={() => onSourceChange(s.value)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
              source === s.value
                ? "bg-gray-900 text-white shadow-sm"
                : "bg-white text-gray-600 border border-gray-200 hover:border-gray-300 hover:bg-gray-50"
            }`}
          >
            {s.label}
          </button>
        ))}

        {/* Clear filters */}
        {hasFilters && (
          <button
            onClick={onClearFilters}
            className="px-3 py-1.5 rounded-full text-xs font-medium text-gray-400 hover:text-gray-600 transition-colors"
          >
            Clear all
          </button>
        )}

        {/* Search */}
        <div className="ml-auto relative">
          <svg
            className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400"
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
            className="pl-8 pr-3 py-1.5 border border-gray-200 rounded-full text-xs bg-white focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-gray-300 w-44 sm:w-56 transition-all"
          />
        </div>
      </div>

      {/* Tag filters with counts */}
      {availableTags.length > 0 && (
        <div className="flex gap-1.5 flex-wrap items-center">
          <span className="text-[10px] text-gray-400 uppercase tracking-wider font-medium mr-1">Tags</span>
          {availableTags.slice(0, 15).map(([tag, count]) => (
            <button
              key={tag}
              onClick={() => onTagToggle(tag)}
              className={`transition-all ${
                selectedTags.includes(tag)
                  ? "ring-2 ring-gray-900 ring-offset-1 rounded"
                  : "opacity-70 hover:opacity-100"
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
