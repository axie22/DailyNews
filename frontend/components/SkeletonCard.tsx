export default function SkeletonCard() {
  return (
    <div className="border border-gray-200 rounded-xl p-4 bg-white">
      <div className="flex items-center gap-2 mb-2.5">
        <div className="skeleton w-12 h-3" />
        <div className="skeleton w-1 h-1 rounded-full" />
        <div className="skeleton w-10 h-3" />
        <div className="ml-auto skeleton w-16 h-2.5" />
      </div>
      <div className="skeleton w-4/5 h-4 mb-2 rounded" />
      <div className="skeleton w-full h-3 mb-1.5 rounded" />
      <div className="skeleton w-3/4 h-3 mb-3 rounded" />
      <div className="flex items-center justify-between">
        <div className="flex gap-1.5">
          <div className="skeleton w-12 h-5 rounded" />
          <div className="skeleton w-14 h-5 rounded" />
          <div className="skeleton w-10 h-5 rounded" />
        </div>
        <div className="skeleton w-12 h-3 rounded" />
      </div>
    </div>
  );
}
