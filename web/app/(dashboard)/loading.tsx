import { CardListSkeleton, PageHeaderSkeleton, Skeleton } from "@/components/Skeleton";

export default function DashboardLoading() {
  return (
    <div className="flex flex-col gap-5">
      <PageHeaderSkeleton />
      <div className="flex gap-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-28 rounded-full" />
        ))}
      </div>
      <CardListSkeleton />
    </div>
  );
}
