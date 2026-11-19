"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

export const DEALER_PAGES = [
  { href: "/agencia/stock", label: "Stock" },
  { href: "/agencia/stock/planilla", label: "Cargar" },
  { href: "/agencia/consultas", label: "Consultas" },
  { href: "/agencia/datos", label: "Datos" },
] as const;

/** The page of the panel a path belongs to (the longest match: /agencia/stock/planilla is «Cargar», /agencia/stock/12 is «Stock»). */
export function dealerPageFor(pathname: string): string | null {
  const path = pathname.replace(/\/+$/, "");
  if (path === "/agencia/stock/nuevo") return "/agencia/stock/planilla";
  let best: string | null = null;
  for (const p of DEALER_PAGES) {
    if ((path === p.href || path.startsWith(`${p.href}/`)) && (!best || p.href.length > best.length)) best = p.href;
  }
  return best;
}

/** Stock · Cargar · Consultas · Datos; scrolls sideways on a phone. */
export function DealerNav({ newLeads = 0 }: { newLeads?: number }) {
  const current = dealerPageFor(usePathname());
  return (
    <nav aria-label="Panel de la agencia" className="-mx-4 overflow-x-auto px-4">
      <ul className="flex gap-1">
        {DEALER_PAGES.map((p) => {
          const active = p.href === current;
          return (
            <li key={p.href}>
              <Link
                href={p.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-sm whitespace-nowrap text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                  active && "bg-foreground font-medium text-background hover:bg-foreground hover:text-background",
                )}
              >
                {p.label}
                {p.href === "/agencia/consultas" && newLeads > 0 ? (
                  <span className="rounded-full bg-mark px-1.5 text-[11px] font-semibold text-[#14213d]">{newLeads}</span>
                ) : null}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
