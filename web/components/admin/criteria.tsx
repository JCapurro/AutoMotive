import { Pill } from "@/components/admin/ui";
import { count, percent } from "@/lib/admin-format";
import type { Database } from "@/types/database";

export type Criterion = Database["public"]["Views"]["v_validation_criteria"]["Row"];

/**
 * The six §53 criteria (v_validation_criteria) as tiles: the value, the
 * threshold and the state in words. Percentages get a meter with the
 * threshold marked on it.
 */
export function CriteriaGrid({ rows }: { rows: Criterion[] }) {
  const met = rows.filter((r) => r.met).length;
  return (
    <div className="space-y-3">
      <p className="text-sm" data-testid="criteria-summary">
        <span className="font-semibold tabular-nums">{met}</span> de {rows.length} criterios cumplidos.
      </p>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="validation-criteria">
        {rows.map((r) => (
          <CriterionTile key={r.criterion} r={r} />
        ))}
      </ul>
    </div>
  );
}

function CriterionTile({ r }: { r: Criterion }) {
  const pct = r.unit === "pct";
  const noData = pct && !r.denominator;
  const value = r.value == null ? null : Number(r.value);
  const threshold = Number(r.threshold ?? 0);
  return (
    <li className="flex flex-col gap-2 rounded-xl bg-card p-4 ring-1 ring-foreground/10" data-criterion={r.criterion}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium">{r.label}</p>
          <p className="text-xs text-muted-foreground">{r.metric}</p>
        </div>
        {noData ? <Pill>Sin datos</Pill> : r.met ? <Pill tone="ok">✓ Cumple</Pill> : <Pill tone="warn">✗ No cumple</Pill>}
      </div>
      <p className="text-3xl font-semibold tracking-tight">
        {noData ? "—" : pct ? percent(value) : count(value)}
      </p>
      {pct ? <Meter value={value ?? 0} threshold={threshold} label={r.label ?? ""} /> : null}
      <p className="text-xs text-muted-foreground">
        Objetivo: ≥ {pct ? percent(threshold) : `${count(threshold)} usuarios`}
        {pct ? ` · ${count(r.numerator)} de ${count(r.denominator)}` : ""}
      </p>
    </li>
  );
}

/**
 * X-01, decision 2: "Contactado" costs a click, so it left criterion 5 and is
 * measured on its own (v_contacted_metric, migration 20261119130000).
 */
export function ContactedMetric({ row }: { row: { users: number | null; events: number | null } | null }) {
  return (
    <p className="text-sm" data-testid="contacted-metric">
      <span className="font-medium">Contactado</span>{" "}
      {row ? (
        <>
          <span className="font-semibold tabular-nums">{count(row.users)}</span> usuarios ·{" "}
          <span className="font-semibold tabular-nums">{count(row.events)}</span> cambios a Contactado
        </>
      ) : (
        <Pill>Sin datos</Pill>
      )}
      <span className="block text-xs text-muted-foreground">Se mide aparte: no cuenta para el criterio 5 (Outcome).</span>
    </p>
  );
}

/** 0–100 track, the fill for the value and a tick at the threshold. */
function Meter({ value, threshold, label }: { value: number; threshold: number; label: string }) {
  const clamp = (v: number) => Math.max(0, Math.min(v, 100));
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={value}
      className="relative h-2 rounded-full bg-sky-100"
    >
      <div className="h-2 rounded-full bg-sky-600" style={{ width: `${clamp(value)}%` }} />
      <div
        aria-hidden
        title={`Objetivo ${threshold}%`}
        className="absolute -top-1 h-4 w-0.5 rounded-full bg-foreground"
        style={{ left: `calc(${clamp(threshold)}% - 1px)` }}
      />
    </div>
  );
}
