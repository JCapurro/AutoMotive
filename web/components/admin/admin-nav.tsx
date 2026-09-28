"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

export const ADMIN_SECTIONS = [
  { href: "/admin", label: "Resumen", exact: true },
  { href: "/admin/metrics", label: "Métricas" },
  { href: "/admin/notifications", label: "Notificaciones" },
  { href: "/admin/matches", label: "Matches" },
  { href: "/admin/users", label: "Usuarios" },
  { href: "/admin/searches", label: "Búsquedas" },
  { href: "/admin/listings", label: "Listings" },
  { href: "/admin/sources", label: "Fuentes" },
  { href: "/admin/errors", label: "Errores" },
  { href: "/admin/config", label: "Config" },
];

/** The backoffice sections (sección 10); scrolls sideways on a phone. */
export function AdminNav() {
  const pathname = usePathname();
  return (
    <nav aria-label="Backoffice" className="-mx-4 overflow-x-auto px-4">
      <ul className="flex gap-1">
        {ADMIN_SECTIONS.map(({ href, label, exact }) => {
          const current = exact ? pathname === href : pathname.startsWith(href);
          return (
            <li key={href}>
              <Link
                href={href}
                aria-current={current ? "page" : undefined}
                className={cn(
                  "inline-flex h-8 items-center rounded-lg px-3 text-sm whitespace-nowrap text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                  current && "bg-muted font-medium text-foreground",
                )}
              >
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
