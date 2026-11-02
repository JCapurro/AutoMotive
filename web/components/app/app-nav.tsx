"use client";

import { Activity, Bookmark, Home, Plus, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";

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
 * Mobile: tab bar (the §55 app tabs, web-sized). The current tab gets the
 * highlighter behind its icon; "Nueva" sits in the middle, reachable from any screen.
 * It slides away while scrolling down so it doesn't cover the page, and comes back
 * on any scroll up, near the top, or at the end of the page.
 */
export function BottomNav({ healthOwner = false }: { healthOwner?: boolean }) {
  const pathname = usePathname();
  const hidden = useHideOnScrollDown();
  const tabs = healthOwner ? [...ITEMS, { href: "/app/health", label: "Health", icon: Activity, exact: true }] : ITEMS;
  const creating = pathname === "/app/searches/new";
  return (
    <nav
      aria-label="Principal"
      className={cn(
        "fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-sm transition-transform duration-200 focus-within:translate-y-0 motion-reduce:transition-none md:hidden",
        hidden && "translate-y-full",
      )}
    >
      <ul className={cn("mx-auto grid max-w-md px-1", healthOwner ? "grid-cols-5" : "grid-cols-4")}>
        {tabs.slice(0, 2).map((tab) => <Tab key={tab.href} {...tab} current={!creating && active(pathname, tab.href, tab.exact)} />)}
        <li>
          <Link
            href="/app/searches/new"
            aria-current={creating ? "page" : undefined}
            className="flex h-14 flex-col items-center justify-center gap-0.5 text-xs font-semibold text-foreground"
          >
            <span className="grid size-8 place-items-center rounded-full bg-primary text-primary-foreground shadow-sm">
              <Plus className="size-5" strokeWidth={2.5} aria-hidden />
            </span>
            Nueva
          </Link>
        </li>
        {tabs.slice(2).map((tab) => <Tab key={tab.href} {...tab} current={active(pathname, tab.href, tab.exact)} />)}
      </ul>
    </nav>
  );
}

function Tab({ href, label, icon: Icon, current }: { href: string; label: string; icon: typeof Home; current: boolean }) {
  return (
    <li>
      <Link
        href={href}
        aria-current={current ? "page" : undefined}
        className={cn(
          "flex h-14 flex-col items-center justify-center gap-0.5 text-xs text-muted-foreground",
          current && "font-semibold text-foreground",
        )}
      >
        <span className={cn("grid h-7 w-12 place-items-center rounded-full transition-colors", current && "bg-mark text-[#14213d]")}>
          <Icon className="size-5" strokeWidth={current ? 2.4 : 2} aria-hidden />
        </span>
        {label}
      </Link>
    </li>
  );
}

// One scroll state for the whole page, so the bottom nav and the listing
// page's action bar above it always agree on where the nav is.
let navHidden = false;
let lastY = 0;
const listeners = new Set<() => void>();

function onScroll() {
  const y = window.scrollY;
  const atEnd = window.innerHeight + y >= document.documentElement.scrollHeight - 8;
  let next = navHidden;
  if (y < 80 || atEnd) {
    next = false;
    lastY = y;
  } else if (Math.abs(y - lastY) > 6) {
    // Measured from the last change, so a slow scroll still counts.
    next = y > lastY;
    lastY = y;
  }
  if (next === navHidden) return;
  navHidden = next;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  if (!listeners.size) {
    lastY = window.scrollY;
    window.addEventListener("scroll", onScroll, { passive: true });
  }
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
    if (listeners.size) return;
    window.removeEventListener("scroll", onScroll);
    navHidden = false;
  };
}

/** True while the reader is scrolling down through the page, past the first screenful (the bottom nav is then hidden). */
export function useHideOnScrollDown() {
  return useSyncExternalStore(subscribe, () => navHidden, () => false);
}
