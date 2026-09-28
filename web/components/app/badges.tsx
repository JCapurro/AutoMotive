import { LEVEL, type InteractionStatus, type Level, STATUS } from "@/lib/copy";
import { cn } from "@/lib/utils";

const LEVEL_STYLE: Record<Level, string> = {
  high: "bg-orange-100 text-orange-900 ring-orange-200",
  good: "bg-emerald-100 text-emerald-900 ring-emerald-200",
  match: "bg-amber-100 text-amber-900 ring-amber-200",
  low: "bg-muted text-muted-foreground ring-border",
};

/** 🔥 88 — the level (§20) and the Opportunity Score. */
export function LevelBadge({
  level,
  score,
  long = false,
  className,
}: {
  level: Level | null;
  score: number | null;
  long?: boolean;
  className?: string;
}) {
  if (!level) return null;
  const { emoji, label } = LEVEL[level];
  return (
    <span
      title={`${label} · Opportunity Score ${score}/100`}
      className={cn(
        "inline-flex h-6 shrink-0 items-center gap-1 rounded-full px-2 text-xs font-semibold tabular-nums ring-1",
        LEVEL_STYLE[level],
        className,
      )}
    >
      <span aria-hidden>{emoji}</span>
      {long ? `${label} · ${score}/100` : score}
    </span>
  );
}

const STATUS_STYLE: Partial<Record<InteractionStatus, string>> = {
  interested: "bg-sky-100 text-sky-900",
  contacted: "bg-violet-100 text-violet-900",
  visit_scheduled: "bg-violet-100 text-violet-900",
  purchased: "bg-emerald-100 text-emerald-900",
  discarded: "bg-muted text-muted-foreground line-through",
};

/** The user's state of a listing (§26). "Nuevo" and "Visto" are quiet on purpose. */
export function StatusBadge({ status }: { status: InteractionStatus | null }) {
  if (!status || status === "seen") return null;
  if (status === "new") {
    return <span className="inline-flex h-5 items-center rounded-full bg-primary px-2 text-[11px] font-medium text-primary-foreground">Nuevo</span>;
  }
  return (
    <span className={cn("inline-flex h-5 items-center rounded-full px-2 text-[11px] font-medium", STATUS_STYLE[status])}>
      {STATUS[status]}
    </span>
  );
}
