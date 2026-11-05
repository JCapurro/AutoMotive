"use client";

import { Activity, Bookmark, Car, ChevronDown, Home, LogOut, Plus, Settings, UserRound } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef } from "react";

import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";


const ITEMS = [
  { href: "/app", label: "Inicio", icon: Home, exact: true },
  { href: "/app/saved", label: "Guardados", icon: Bookmark },
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

/**
 * Top right, on desktop and mobile (Juan 04/11): the account. Mis datos,
 * Ajustes and signing out live here, so the header keeps only the places
 * people go to work.
 */
export function AccountMenu({ email }: { email: string | null }) {
  const pathname = usePathname();
  const signOut = useRef<HTMLFormElement>(null);
  const current = pathname.startsWith("/app/datos") || pathname.startsWith("/app/settings") || pathname.startsWith("/app/cuenta");
  return (
    <>
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>
          {/* Juan, 04/11: the car with the arrow, not the email's initial. */}
          <button type="button" aria-label="Tu cuenta" title="Tu cuenta" data-testid="account-menu"
            className="group flex h-full shrink-0 items-center gap-0.5 px-1 text-muted-foreground outline-none hover:text-foreground focus-visible:text-foreground">
            <span className={cn(
              "grid size-8 place-items-center rounded-full border bg-muted text-foreground transition-colors",
              current && "border-transparent bg-mark text-[#14213d]",
            )}>
              <Car className="size-4.5" aria-hidden />
            </span>
            <ChevronDown className="size-3.5 transition-transform group-data-[state=open]:rotate-180" aria-hidden />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" sideOffset={2} className="w-64">
          {email ? <DropdownMenuLabel className="text-sm font-normal [overflow-wrap:anywhere]">
            <span className="block text-xs text-muted-foreground">Entraste como</span>
            <span className="font-medium text-foreground">{email}</span>
          </DropdownMenuLabel> : null}
          {email ? <DropdownMenuSeparator /> : null}
          <DropdownMenuItem asChild className="py-2">
            <Link href="/app/datos"><UserRound aria-hidden /> Mis datos</Link>
          </DropdownMenuItem>
          <DropdownMenuItem asChild className="py-2">
            <Link href="/app/settings"><Settings aria-hidden /> Ajustes</Link>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          {/* The form sits outside the menu: closing the menu would unmount it mid-submit. */}
          <DropdownMenuItem className="py-2" onSelect={() => signOut.current?.requestSubmit()}>
            <LogOut aria-hidden /> Cerrar sesión
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <form ref={signOut} action="/auth/signout" method="post" hidden />
    </>
  );
}
