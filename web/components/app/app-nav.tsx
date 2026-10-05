"use client";

import { Activity, Bookmark, CreditCard, Home, Plus, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";


const ITEMS = [
  { href: "/app", label: "Inicio", icon: Home, exact: true },
  { href: "/app/saved", label: "Guardados", icon: Bookmark },
  { href: "/app/pro", label: "Planes", icon: CreditCard },
  { href: "/app/settings", label: "Ajustes", icon: Settings },
];

function active(pathname: string, href: string, exact?: boolean) {
  return exact ? pathname === href || pathname.startsWith("/app/searches") : pathname.startsWith(href);
}

/** Desktop: links in the header. */
export function TopNav({ admin = false, healthOwner = false }: { admin?: boolean; healthOwner?: boolean }) {
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
      <Button asChild className="my-auto ml-auto h-9 px-3.5">
        <Link href="/app/searches/new">
          <Plus aria-hidden /> Nueva búsqueda
        </Link>
      </Button>
    </nav>
  );
}

/** Mobile: tab bar (the §55 app tabs, web-sized). */
export function BottomNav({ healthOwner = false }: { healthOwner?: boolean }) {
  const pathname = usePathname();
  const items = healthOwner ? [...ITEMS, { href: "/app/health", label: "Health", icon: Activity, exact: true }] : ITEMS;
  return (
    <nav
      aria-label="Principal"
      className="fixed inset-x-0 bottom-0 z-40 border-t bg-background pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      <ul className={cn("mx-auto grid max-w-md", healthOwner ? "grid-cols-5" : "grid-cols-4")}>
        {items.map(({ href, label, icon: Icon, exact }) => {
          const current = active(pathname, href, exact);
          return (
            <li key={href}>
              <Link
                href={href}
                aria-current={current ? "page" : undefined}
                className={cn(
                  "relative flex h-15 flex-col items-center justify-center gap-0.5 text-[11px] text-muted-foreground",
                  current && "font-semibold text-foreground",
                )}
              >
                <Icon className="size-5" aria-hidden />
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
