import type { ReactNode } from "react";

type Source = "arxiv" | "huggingface" | "rss" | "x";

const SOURCE_CONFIG: Record<Source, { label: string; color: string; darkColor: string; icon: ReactNode }> = {
  arxiv: {
    label: "arXiv",
    color: "text-red-600 bg-red-50 border-red-200",
    darkColor: "dark:text-red-400 dark:bg-red-950 dark:border-red-800",
    icon: <span className="font-black text-[9px] leading-none">arX</span>,
  },
  huggingface: {
    label: "HF",
    color: "text-yellow-600 bg-yellow-50 border-yellow-200",
    darkColor: "dark:text-yellow-400 dark:bg-yellow-950 dark:border-yellow-800",
    icon: <span className="text-[11px] leading-none">🤗</span>,
  },
  rss: {
    label: "RSS",
    color: "text-orange-500 bg-orange-50 border-orange-200",
    darkColor: "dark:text-orange-400 dark:bg-orange-950 dark:border-orange-800",
    icon: (
      <svg className="w-2.5 h-2.5" viewBox="0 0 8 8" fill="currentColor">
        <circle cx="1" cy="7" r="1" />
        <path d="M0 4c2.2 0 4 1.8 4 4H3C3 6.3 1.7 5 0 5V4z" />
        <path d="M0 1c3.9 0 7 3.1 7 7H6C6 4.7 3.3 2 0 2V1z" />
      </svg>
    ),
  },
  x: {
    label: "X",
    color: "text-gray-700 bg-gray-100 border-gray-200",
    darkColor: "dark:text-gray-200 dark:bg-gray-800 dark:border-gray-700",
    icon: (
      <svg className="w-2.5 h-2.5" viewBox="0 0 24 24" fill="currentColor">
        <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.737-8.835L1.254 2.25H8.08l4.26 5.632L18.244 2.25zm-1.161 17.52h1.833L7.084 4.126H5.117L17.083 19.77z" />
      </svg>
    ),
  },
};

export default function SourceBadge({ source }: { source: string }) {
  const config = SOURCE_CONFIG[source as Source];
  if (!config) return <span className="text-[11px] text-gray-400 dark:text-gray-500">{source}</span>;

  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold border ${config.color} ${config.darkColor}`}>
      {config.icon}
      {config.label}
    </span>
  );
}
