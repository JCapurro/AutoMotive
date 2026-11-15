"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import { cn } from "@/lib/utils";

export type AdminPage = { href: string; label: string };
export type AdminArea = { id: string; label: string; pages: AdminPage[] };

/**
 * The backoffice menu: areas, each with its pages. URLs never change; only the
 * grouping does. To add a page, add ONE line to the `pages` of its area:
 * `{ href: "/admin/foo", label: "Foo" }`. A page whose href carries `?view=…`
 * is one of the three views of /admin/metrics (activation, revenue, operation).
 */
export const ADMIN_AREAS: AdminArea[] = [
  { id: "hoy", label: "Hoy", pages: [
    { href: "/admin", label: "Hoy" },
  ] },
  { id: "crecimiento", label: "Crecimiento", pages: [
    { href: "/admin/users", label: "Usuarios" },
    { href: "/admin/experiments", label: "Experimentos" },
    { href: "/admin/metrics?view=activation", label: "Activación" },
  ] },
  { id: "calidad", label: "Calidad", pages: [
    { href: "/admin/matches", label: "Matches" },
    { href: "/admin/matches/audit", label: "Auditoría" },
    { href: "/admin/searches", label: "Búsquedas" },
    { href: "/admin/catalog-misses", label: "Modelos pedidos" },
  ] },
  { id: "ingresos", label: "Ingresos", pages: [
    { href: "/admin/billing", label: "Cobros" },
    { href: "/admin/metrics?view=revenue", label: "Ingresos" },
  ] },
  { id: "operacion", label: "Operación", pages: [
    { href: "/admin/sources", label: "Fuentes" },
    { href: "/admin/errors", label: "Errores" },
    { href: "/admin/metrics?view=operation", label: "Operación" },
  ] },
  { id: "herramientas", label: "Herramientas", pages: [
    { href: "/admin/listings", label: "Listings" },
    { href: "/admin/notifications", label: "Notificaciones" },
    { href: "/admin/guides", label: "Guías" },
    { href: "/admin/config", label: "Config" },
    { href: "/admin/metrics/diagnostic", label: "Diagnóstico" },
  ] },
];

const METRICS_PATH = "/admin/metrics";

/** The metrics view a `view` query param selects; mirrors app/admin/metrics/page.tsx. */
function metricsView(view: string | null | undefined): string {
  return view === "revenue" || view === "operation" ? view : "activation";
}

function split(href: string): { path: string; view: string | null } {
  const [path, query = ""] = href.split("?");
  return { path, view: new URLSearchParams(query).get("view") };
}

/**
 * The area and page that `pathname` (+ the metrics `view` param) belong to.
 * Detail pages (/admin/users/123) keep their parent's page; /admin/metrics/diagnostic
 * is its own page and never lights a metrics view.
 */
export function resolveAdminNav(pathname: string, view?: string | null, areas: AdminArea[] = ADMIN_AREAS): { area: AdminArea; page: AdminPage } | null {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  let best: { area: AdminArea; page: AdminPage; length: number } | null = null;
  for (const area of areas) {
    for (const page of area.pages) {
      const target = split(page.href);
      let matches: boolean;
      if (target.view) matches = path === target.path && metricsView(view) === target.view;
      else if (target.path === "/admin") matches = path === "/admin";
      else if (target.path === METRICS_PATH) matches = path === METRICS_PATH;
      else matches = path === target.path || path.startsWith(`${target.path}/`);
      if (matches && (!best || target.path.length > best.length)) best = { area, page, length: target.path.length };
    }
  }
  return best && { area: best.area, page: best.page };
}

const pill = "inline-flex items-center rounded-lg whitespace-nowrap transition-colors";

/** Two rows: the areas, and the pages of the active one; both scroll sideways on a phone. */
export function AdminNav() {
  return <AdminNavView pathname={usePathname()} view={useSearchParams().get("view")} />;
}

export function AdminNavView({ pathname, view }: { pathname: string; view?: string | null }) {
  const current = resolveAdminNav(pathname, view);
  const area = current?.area;

  return (
    <div className="space-y-1">
      <nav aria-label="Áreas del backoffice" className="-mx-4 overflow-x-auto px-4">
        <ul className="flex gap-1">
          {ADMIN_AREAS.map((a) => {
            const active = a.id === area?.id;
            return (
              <li key={a.id}>
                <Link
                  href={a.pages[0].href}
                  aria-current={active ? "page" : undefined}
                  className={cn(pill, "h-8 px-3 text-sm text-muted-foreground hover:bg-muted hover:text-foreground", active && "bg-foreground font-medium text-background hover:bg-foreground hover:text-background")}
                >
                  {a.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      {area && area.pages.length > 1 ? (
        <nav aria-label={`Páginas de ${area.label}`} className="-mx-4 overflow-x-auto px-4">
          <ul className="flex gap-1">
            {area.pages.map((p) => {
              const active = p.href === current?.page.href;
              return (
                <li key={p.href}>
                  <Link
                    href={p.href}
                    aria-current={active ? "page" : undefined}
                    className={cn(pill, "h-7 px-2.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground", active && "bg-muted font-medium text-foreground")}
                  >
                    {p.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      ) : null}
    </div>
  );
}
