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
    <nav aria-label="Principal" className="hidden h-full flex-1 items-stretch gap-1 md:flex">
      {ITEMS.map(({ href, label, badge, exact }) => (
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
          {badge ? <UnreadBadge /> : null}
        </Link>
      ))}
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

/** Mobile: the inbox bell in the header. */
export function MobileInboxLink() {
  return (
    <Link href="/app/inbox" aria-label="Alertas" className="relative ml-auto inline-flex size-10 items-center justify-center md:hidden">
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
      className="fixed inset-x-0 bottom-0 z-40 border-t bg-background pb-[env(safe-area-inset-bottom)] md:hidden"
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
                  "relative flex h-15 flex-col items-center justify-center gap-0.5 text-[11px] text-muted-foreground",
                  current && "font-semibold text-foreground",
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
