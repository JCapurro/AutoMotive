"use client";

import { Bell, Bookmark, Home, Plus, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { UnreadBadge } from "./inbox-provider";

const ITEMS = [
  { href: "/app", label: "Inicio", icon: Home, exact: true },
  { href: "/app/saved", label: "Guardados", icon: Bookmark },
  { href: "/app/inbox", label: "Alertas", icon: Bell, badge: true },
  { href: "/app/settings", label: "Ajustes", icon: Settings },
];

function active(pathname: string, href: string, exact?: boolean) {
  return exact ? pathname === href || pathname.startsWith("/app/searches") : pathname.startsWith(href);
}

/** Desktop: links in the header. */
export function TopNav({ admin = false }: { admin?: boolean }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Principal" className="hidden items-center gap-1 md:flex">
      {ITEMS.map(({ href, label, badge, exact }) => (
        <Link
          key={href}
          href={href}
          aria-current={active(pathname, href, exact) ? "page" : undefined}
          className={cn(
            "inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
            active(pathname, href, exact) && "bg-muted font-medium text-foreground",
          )}
        >
          {label}
          {badge ? <UnreadBadge /> : null}
        </Link>
      ))}
      {admin ? (
        <Link href="/admin" className="inline-flex h-8 items-center rounded-lg px-3 text-sm text-muted-foreground hover:bg-muted hover:text-foreground">
          Admin
        </Link>
      ) : null}
      <Button asChild size="sm" className="ml-2">
        <Link href="/app/searches/new">
          <Plus aria-hidden /> Nueva búsqueda
        </Link>
      </Button>
    </nav>
  );
}

/** Mobile: the inbox bell in the header. */
export function MobileInboxLink() {
  return (
    <Link href="/app/inbox" aria-label="Alertas" className="relative inline-flex size-9 items-center justify-center md:hidden">
      <Bell className="size-5" aria-hidden />
      <UnreadBadge className="absolute -top-0.5 -right-1" />
    </Link>
  );
}

/** Mobile: tab bar (the §55 app tabs, web-sized). */
export function BottomNav() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Principal"
      className="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
    >
      <ul className="mx-auto grid max-w-md grid-cols-4">
        {ITEMS.map(({ href, label, icon: Icon, badge, exact }) => {
          const current = active(pathname, href, exact);
          return (
            <li key={href}>
              <Link
                href={href}
                aria-current={current ? "page" : undefined}
                className={cn(
                  "relative flex h-14 flex-col items-center justify-center gap-0.5 text-[11px] text-muted-foreground",
                  current && "font-medium text-foreground",
                )}
              >
                <Icon className="size-5" aria-hidden />
                {label}
                {badge ? <UnreadBadge className="absolute top-1.5 left-1/2 ml-1.5" /> : null}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
