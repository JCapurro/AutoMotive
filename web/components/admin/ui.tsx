import Link from "next/link";

import { cn } from "@/lib/utils";

/** Building blocks of the /admin pages (sección 10): dense, text-first tables. */

export function PageHeader({ title, description, children }: { title: string; description?: string; children?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0 space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {children}
    </div>
  );
}

export function Section({ title, description, children, className }: {
  title: string;
  description?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("space-y-3", className)}>
      <div className="space-y-0.5">
        <h2 className="text-base font-semibold tracking-tight">{title}</h2>
        {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
      </div>
      {children}
    </section>
  );
}

/** A horizontally scrollable table: wide on desktop, swipeable at 375 px. */
export function Table({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("relative overflow-x-auto rounded-xl bg-card ring-1 ring-foreground/10", className)}>
      <table className="w-full text-left text-sm">{children}</table>
    </div>
  );
}

export function Th({ children, className, numeric }: { children?: React.ReactNode; className?: string; numeric?: boolean }) {
  return (
    <th
      scope="col"
      className={cn(
        "border-b px-3 py-2 text-xs font-medium whitespace-nowrap text-muted-foreground",
        numeric && "text-right",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function Td({ children, className, numeric }: { children?: React.ReactNode; className?: string; numeric?: boolean }) {
  return (
    <td className={cn("border-b px-3 py-2 align-top last:border-b-0 [tr:last-child_&]:border-b-0", numeric && "text-right tabular-nums", className)}>
      {children}
    </td>
  );
}

export function EmptyRow({ colSpan, children = "Sin datos todavía." }: { colSpan: number; children?: React.ReactNode }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-3 py-6 text-center text-sm text-muted-foreground">
        {children}
      </td>
    </tr>
  );
}

/** A stat tile: label, value and an optional note. */
export function Stat({ label, value, note }: { label: string; value: React.ReactNode; note?: React.ReactNode }) {
  return (
    <div className="space-y-1 rounded-xl bg-card p-3 ring-1 ring-foreground/10">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-2xl font-semibold tracking-tight">{value}</p>
      {note ? <p className="text-xs text-muted-foreground">{note}</p> : null}
    </div>
  );
}

const PILL: Record<string, string> = {
  ok: "bg-emerald-50 text-emerald-900 ring-emerald-200",
  warn: "bg-amber-50 text-amber-950 ring-amber-200",
  bad: "bg-red-50 text-red-900 ring-red-200",
  muted: "bg-muted text-muted-foreground ring-border",
};

/** Status text with its tone; the text always says the state (never color alone). */
export function Pill({ tone = "muted", children }: { tone?: keyof typeof PILL; children: React.ReactNode }) {
  return (
    <span className={cn("inline-flex h-5 items-center gap-1 rounded-full px-2 text-xs font-medium whitespace-nowrap ring-1", PILL[tone])}>
      {children}
    </span>
  );
}

export function TextLink({ href, children, className }: { href: string; children: React.ReactNode; className?: string }) {
  return (
    <Link href={href} className={cn("font-medium underline-offset-2 hover:underline", className)}>
      {children}
    </Link>
  );
}

/** Pretty JSON for the inspector and config. */
export function Json({ value, className }: { value: unknown; className?: string }) {
  return (
    <pre className={cn("overflow-x-auto rounded-lg bg-muted p-3 font-mono text-xs leading-relaxed", className)}>
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}
