"use client";

import { useState } from "react";

const SOURCES = [
  { value: "", label: "All" },
  { value: "arxiv", label: "arXiv" },
  { value: "huggingface", label: "Hugging Face" },
  { value: "rss", label: "RSS" },
  { value: "x", label: "X" },
];

interface FilterBarProps {
  source: string;
  selectedTags: string[];
  availableTags: string[];
  search: string;
  onSourceChange: (s: string) => void;
  onTagToggle: (tag: string) => void;
  onSearchChange: (q: string) => void;
}

export default function FilterBar({
  source,
  selectedTags,
  availableTags,
  search,
  onSourceChange,
  onTagToggle,
  onSearchChange,
}: FilterBarProps) {
  return (
    <div className="mb-6 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        {SOURCES.map((s) => (
          <button
            key={s.value}
            onClick={() => onSourceChange(s.value)}
            className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
              source === s.value
                ? "bg-gray-900 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {s.label}
          </button>
        ))}
        <input
          type="text"
          placeholder="Search..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="ml-auto px-3 py-1 border rounded-full text-sm focus:outline-none focus:ring-2 focus:ring-gray-300"
        />
      </div>
      {availableTags.length > 0 && (
        <div className="flex gap-1.5 flex-wrap">
          {availableTags.slice(0, 15).map(([tag]) => (
            <button
              key={tag}
              onClick={() => onTagToggle(tag)}
              className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                selectedTags.includes(tag)
                  ? "bg-gray-900 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {tag}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
