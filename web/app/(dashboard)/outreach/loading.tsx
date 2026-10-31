import { Skeleton, TableSkeleton } from "@/components/Skeleton";

export default function OutreachLoading() {
  return (
    <div className="flex flex-col gap-4">
      <Skeleton className="h-10 w-36" />
      <TableSkeleton rows={5} />
    </div>
  );
}
