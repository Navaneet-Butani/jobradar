/**
 * Skeletons mirror the shape of what is loading rather than spinning, so the
 * layout does not jump when data lands. Every page in this app is
 * server-rendered against a backend that cold-starts in ~50s on the free tier,
 * which makes the loading state a real state, not a formality.
 */

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-bg-sunken ${className}`} aria-hidden />;
}

export function PageHeaderSkeleton() {
  return (
    <div className="border-b border-border pb-5">
      <Skeleton className="h-6 w-44" />
      <Skeleton className="mt-2 h-4 w-80" />
      <Skeleton className="mt-3 h-4 w-56" />
    </div>
  );
}

export function CardListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="rounded-xl border border-border bg-bg-elevated p-4 sm:p-5">
          <div className="flex items-start gap-4">
            <div className="min-w-0 flex-1">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="mt-2.5 h-5 w-2/3" />
              <div className="mt-3 flex gap-3">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-4 w-20" />
              </div>
              <Skeleton className="mt-3 h-9 w-full" />
            </div>
            <Skeleton className="h-14 w-14 shrink-0 rounded-full" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function TableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="overflow-hidden rounded-xl border border-border">
      <div className="border-b border-border bg-bg-sunken px-3 py-2.5">
        <Skeleton className="h-3 w-32" />
      </div>
      <div className="divide-y divide-border">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 bg-bg-elevated px-3 py-3">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-48" />
          </div>
        ))}
      </div>
    </div>
  );
}
