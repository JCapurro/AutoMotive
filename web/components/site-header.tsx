import Link from "next/link";

import { Logo } from "@/components/logo";
import { cn } from "@/lib/utils";

export function SiteHeader({ signedIn, page }: { signedIn: boolean; page: "home" | "pricing" }) {
  return (
    <header className="border-b">
      <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-x-4 gap-y-3 px-4 py-4 sm:px-6 lg:px-10">
        <Logo />
        <nav aria-label="Navegación principal" className="order-last flex w-full gap-6 sm:order-none sm:ml-auto sm:w-auto">
          {[
            { href: "/", label: "Inicio", key: "home" },
            { href: "/pricing", label: "Pricing", key: "pricing" },
          ].map((item) => (
            <Link
              key={item.key}
              href={item.href}
              aria-current={page === item.key ? "page" : undefined}
              className={cn(
                "border-b-2 px-1 py-2 text-[15px] font-medium transition-colors hover:text-foreground",
                page === item.key ? "border-foreground text-foreground" : "border-transparent text-muted-foreground",
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <Link href={signedIn ? "/app" : "/login"} className="ml-auto px-1 py-2 text-[15px] font-medium underline-offset-4 hover:underline sm:ml-6">
          {signedIn ? "Mis búsquedas" : "Ingresar"}
        </Link>
      </div>
    </header>
  );
}
