import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Cargando">
      <Skeleton className="h-7 w-48" />
      <div className="grid gap-3 sm:grid-cols-2">
        <Skeleton className="h-28 rounded-xl" />
        <Skeleton className="h-28 rounded-xl" />
      </div>
      <Skeleton className="h-24 rounded-xl" />
      <Skeleton className="h-24 rounded-xl" />
    </div>
  );
}
