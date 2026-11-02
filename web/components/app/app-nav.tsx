"use client";

import { Activity, Bookmark, Home, Plus, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";


const ITEMS = [
  { href: "/app", label: "Inicio", icon: Home, exact: true },
  { href: "/app/saved", label: "Guardados", icon: Bookmark },
  { href: "/app/settings", label: "Ajustes", icon: Settings },
];

function active(pathname: string, href: string, exact?: boolean) {
  return exact ? pathname === href || pathname.startsWith("/app/searches") : pathname.startsWith(href);
}

/** Desktop: links in the header. */
export function TopNav({ admin = false, healthOwner = false, canAcquirePlan }: { admin?: boolean; healthOwner?: boolean; canAcquirePlan: boolean }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Principal" className="hidden h-full flex-1 items-stretch gap-1 md:flex">
      {ITEMS.map(({ href, label, exact }) => (
        <Link
          key={href}
          href={href}
          aria-current={active(pathname, href, exact) ? "page" : undefined}
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 text-[15px] text-muted-foreground transition-colors hover:text-foreground",
            active(pathname, href, exact) && "font-semibold text-foreground shadow-[inset_0_-3px_0_var(--foreground)]",
          )}
        >
          {label}
        </Link>
      ))}
      {healthOwner ? <Link href="/app/health" aria-current={pathname === "/app/health" ? "page" : undefined} className="inline-flex items-center px-2.5 text-[15px] text-muted-foreground hover:text-foreground">Health</Link> : null}
      {admin ? (
        <Link href="/admin" className="inline-flex items-center px-2.5 text-[15px] text-muted-foreground hover:text-foreground">
          Admin
        </Link>
      ) : null}
      <div className="my-auto ml-auto flex items-center gap-2">
        <AcquirePlanButton canAcquirePlan={canAcquirePlan} />
        <Button asChild className="h-9 px-3.5">
          <Link href="/app/searches/new">
            <Plus aria-hidden /> Nueva búsqueda
          </Link>
        </Button>
      </div>
    </nav>
  );
}

/** Desktop and mobile share the same plan acquisition rule. */
export function AcquirePlanButton({ canAcquirePlan, className }: { canAcquirePlan: boolean; className?: string }) {
  if (!canAcquirePlan) return null;
  return (
    <Button asChild variant="outline" className={cn("h-9 px-3.5", className)}>
      <Link href="/app/pro">Planes</Link>
    </Button>
  );
}

/**
 * Mobile: the same places as icons in the header, next to the logo (Juan 02/11:
 * no bottom tab bar, so the screen stays clean). The current one gets the
 * highlighter behind its icon; "Nueva" closes the row, as on desktop. Each link
 * takes the header's full height, so the touch target stays tall.
 */
export function MobileNav({ healthOwner = false }: { healthOwner?: boolean }) {
  const pathname = usePathname();
  const tabs = healthOwner ? [...ITEMS, { href: "/app/health", label: "Health", icon: Activity, exact: true }] : ITEMS;
  const creating = pathname === "/app/searches/new";
  return (
    <nav aria-label="Principal" className="flex h-full items-stretch">
      {tabs.map(({ href, label, icon: Icon, exact }) => {
        const current = !creating && active(pathname, href, exact);
        return (
          <Link
            key={href}
            href={href}
            aria-label={label}
            title={label}
            aria-current={current ? "page" : undefined}
            className={cn("grid w-9 place-items-center text-muted-foreground hover:text-foreground", current && "text-foreground")}
          >
            <span className={cn("grid size-8 place-items-center rounded-full transition-colors", current && "bg-mark text-[#14213d]")}>
              <Icon className="size-5" strokeWidth={current ? 2.4 : 2} aria-hidden />
            </span>
          </Link>
        );
      })}
      <Link
        href="/app/searches/new"
        aria-label="Nueva búsqueda"
        title="Nueva búsqueda"
        aria-current={creating ? "page" : undefined}
        className="grid w-10 place-items-center"
      >
        <span className="grid size-8 place-items-center rounded-full bg-primary text-primary-foreground shadow-sm">
          <Plus className="size-5" strokeWidth={2.5} aria-hidden />
        </span>
      </Link>
    </nav>
  );
}
