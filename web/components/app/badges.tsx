import { LEVEL, type InteractionStatus, type Level, STATUS } from "@/lib/copy";
import { cn } from "@/lib/utils";

/**
 * The Opportunity Score marked like the level (§20): an opportunity gets the
 * full highlighter, a good match a stroke underneath, a plain match nothing and
 * low priority fades. The level's name goes next to it (`long`) or, read aloud
 * only, inside the number's label.
 */
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
  const { label } = LEVEL[level];
  return (
    <span
      title={`${label} · Opportunity Score ${score}/100`}
      className={cn("inline-flex shrink-0 flex-col items-end gap-1 text-right", className)}
    >
      <span className={cn("type-figure text-[22px] leading-none", level === "low" && "text-faint")}>
        <span className={level === "high" ? "mark" : level === "good" ? "mark-under" : undefined}>{score}</span>
        {long ? null : <span className="sr-only"> {label}</span>}
      </span>
      {long ? <span className="text-xs font-medium text-muted-foreground">{label}</span> : null}
    </span>
  );
}

const STATUS_STYLE: Partial<Record<InteractionStatus, string>> = {
  interested: "ring-1 ring-foreground ring-inset",
  contacted: "bg-panel-2",
  visit_scheduled: "bg-panel-2",
  purchased: "bg-ok text-white",
  discarded: "px-0 text-faint line-through",
};

/** The user's state of a listing (§26). "Nuevo" and "Visto" are quiet on purpose. */
export function StatusBadge({ status }: { status: InteractionStatus | null }) {
  if (!status || status === "seen") return null;
  if (status === "new") {
    return <span className="inline-flex h-5.5 items-center rounded px-2 text-xs font-semibold bg-primary text-primary-foreground">Nuevo</span>;
  }
  return (
    <span className={cn("inline-flex h-5.5 items-center rounded px-2 text-xs font-semibold", STATUS_STYLE[status])}>
      {STATUS[status]}
    </span>
  );
}
