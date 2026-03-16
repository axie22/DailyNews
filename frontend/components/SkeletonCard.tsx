export default function SkeletonCard() {
  return (
    <div className="border border-gray-200 rounded-xl p-4 bg-white">
      <div className="flex items-center gap-2 mb-3">
        <div className="skeleton w-14 h-5 rounded-md" />
        <div className="skeleton w-12 h-3" />
      </div>
      <div className="skeleton w-3/4 h-4 mb-2" />
      <div className="skeleton w-full h-3 mb-1.5" />
      <div className="skeleton w-5/6 h-3 mb-3" />
      <div className="flex gap-1.5">
        <div className="skeleton w-12 h-5 rounded" />
        <div className="skeleton w-16 h-5 rounded" />
      </div>
    </div>
  );
}
