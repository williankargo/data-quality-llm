interface LoadingSkeletonProps {
  lines?: number;
}

export function LoadingSkeleton({ lines = 3 }: LoadingSkeletonProps) {
  return (
    <div className="space-y-2 animate-pulse">
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="h-4 bg-gray-200 rounded"
          style={{ width: `${60 + (i % 3) * 15}%` }}
        />
      ))}
    </div>
  );
}
