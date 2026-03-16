const TAG_COLORS: Record<string, string> = {
  LLMs: "bg-purple-100 text-purple-700",
  RL: "bg-green-100 text-green-700",
  Vision: "bg-blue-100 text-blue-700",
  Multimodal: "bg-indigo-100 text-indigo-700",
  Efficiency: "bg-yellow-100 text-yellow-700",
  Alignment: "bg-red-100 text-red-700",
  Robotics: "bg-orange-100 text-orange-700",
  Diffusion: "bg-pink-100 text-pink-700",
  Audio: "bg-cyan-100 text-cyan-700",
  Theory: "bg-gray-200 text-gray-700",
  Infrastructure: "bg-slate-100 text-slate-700",
  Dataset: "bg-teal-100 text-teal-700",
  Benchmark: "bg-lime-100 text-lime-700",
  Other: "bg-gray-100 text-gray-500",
};

interface TagBadgeProps {
  tag: string;
  count?: number;
  onClick?: () => void;
}

export default function TagBadge({ tag, count, onClick }: TagBadgeProps) {
  const color = TAG_COLORS[tag] ?? "bg-gray-100 text-gray-600";
  return (
    <span
      onClick={onClick}
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium ${color} ${
        onClick ? "cursor-pointer hover:opacity-80" : "cursor-default"
      }`}
    >
      {tag}
      {count !== undefined && (
        <span className="opacity-50 text-[10px]">{count}</span>
      )}
    </span>
  );
}
