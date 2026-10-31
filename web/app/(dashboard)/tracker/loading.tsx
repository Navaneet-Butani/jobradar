import { PageHeaderSkeleton, Skeleton } from "@/components/Skeleton";

export default function TrackerLoading() {
  return (
    <div className="flex flex-col gap-5">
      <PageHeaderSkeleton />
      <div className="flex gap-4 overflow-hidden">
        {Array.from({ length: 4 }).map((_, col) => (
          <div key={col} className="flex w-72 shrink-0 flex-col gap-3 rounded-xl border border-border bg-bg-sunken p-3">
            <Skeleton className="h-3 w-20" />
            {Array.from({ length: col === 0 ? 2 : 1 }).map((_, card) => (
              <div key={card} className="rounded-lg border border-border bg-bg-elevated p-3">
                <Skeleton className="h-4 w-4/5" />
                <Skeleton className="mt-2 h-3 w-1/2" />
                <Skeleton className="mt-3 h-3 w-2/3" />
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
