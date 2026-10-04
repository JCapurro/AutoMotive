import Link from "next/link";
import { accessDescription, type PlanLimits } from "@/lib/pro";

export function PlanStatus({ access }: { access: PlanLimits | null }) {
  if (!access || access.state === "pilot") return null;
  return <aside aria-label="Estado de tu plan" className="mb-5 flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-card px-4 py-3 text-sm">
    <p>{accessDescription(access)}</p>
    <Link href="/app/pro" className="shrink-0 font-medium underline underline-offset-4">Ver planes</Link>
  </aside>;
}
