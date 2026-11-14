import Link from "next/link";

import { count } from "@/lib/admin-format";
import { cn } from "@/lib/utils";

/** Pieces of the dashboard pages (Usuarios, Búsquedas): tabs as links, bar lists, rates. */

export function LinkTabs({ items, current, label }: { items: { href: string; label: string; key: string }[]; current: string; label: string }) {
  return (
    <nav aria-label={label} className="flex flex-wrap gap-1 rounded-lg bg-muted p-1">
      {items.map((it) => (
        <Link
          key={it.key}
          href={it.href}
          aria-current={it.key === current ? "page" : undefined}
          className={cn(
            "inline-flex h-7 items-center rounded-md px-2.5 text-xs whitespace-nowrap text-muted-foreground hover:text-foreground",
            it.key === current && "bg-background font-medium text-foreground shadow-sm",
          )}
        >
          {it.label}
        </Link>
      ))}
    </nav>
  );
}

/** A ranked list with a bar per row; the number is always written next to it. */
export function BarList({ rows, total, empty = "Sin datos todavía.", href }: {
  rows: { label: string; value: number; note?: string; key?: string }[];
  total?: number;
  empty?: string;
  href?: (key: string) => string;
}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  if (!rows.length) return <p className="text-sm text-muted-foreground">{empty}</p>;
  return (
    <ul className="space-y-1.5">
      {rows.map((r) => {
        const label = href && r.key ? <Link href={href(r.key)} className="hover:underline">{r.label}</Link> : r.label;
        return (
          <li key={r.key ?? r.label} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 text-sm">
            <div className="relative min-w-0 overflow-hidden rounded-md">
              <div className="absolute inset-y-0 left-0 rounded-md bg-primary/15" style={{ width: `${(r.value / max) * 100}%` }} aria-hidden />
              <span className="relative block truncate px-2 py-1">{label}</span>
            </div>
            <span className="text-right tabular-nums">
              {count(r.value)}
              {total ? <span className="ml-1 text-xs text-muted-foreground">{rate(r.value, total)}</span> : null}
              {r.note ? <span className="ml-1 text-xs text-muted-foreground">{r.note}</span> : null}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export function rate(part: number, total: number): string {
  if (!total) return "—";
  const r = Math.round((part / total) * 100);
  return part > 0 && r === 0 ? "<1%" : `${r}%`;
}

/** A card around a block of the dashboard. */
export function Card({ title, description, children, className }: { title: string; description?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("min-w-0 space-y-3 rounded-xl bg-card p-4 ring-1 ring-foreground/10", className)}>
      <div className="space-y-0.5">
        <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
        {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
      </div>
      {children}
    </section>
  );
}

/** A heat cell: the shade follows the share, the text always says it. */
export function HeatCell({ value }: { value: number | null }) {
  if (value == null) return <td className="px-2 py-1.5 text-center text-xs text-muted-foreground">…</td>;
  return (
    <td className="px-2 py-1.5 text-center text-xs tabular-nums" style={{ backgroundColor: `color-mix(in oklab, var(--primary) ${Math.round(value * 0.6)}%, transparent)` }}>
      {value}%
    </td>
  );
}

/** Builds a query string from the current params with some keys replaced (null drops a key). */
export function withParams(path: string, params: Record<string, string | undefined>, change: Record<string, string | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries({ ...params, ...change })) if (v != null && v !== "") q.set(k, v);
  const s = q.toString();
  return s ? `${path}?${s}` : path;
}
