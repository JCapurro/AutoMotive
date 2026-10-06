import Link from "next/link";

import { Logo } from "@/components/logo";
import { cn } from "@/lib/utils";

export function SiteHeader({ signedIn, page }: { signedIn: boolean; page: "home" | "pricing" }) {
  return (
    <header className="border-b">
      <div className="mx-auto grid w-full max-w-6xl grid-cols-2 items-center gap-x-4 gap-y-3 px-4 py-4 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:px-6 lg:px-10">
        <Logo className="justify-self-start" />
        <nav aria-label="Navegación principal" className="col-span-2 row-start-2 flex justify-center gap-6 sm:col-span-1 sm:col-start-2 sm:row-start-1">
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
        <Link href={signedIn ? "/app" : "/login"} className="col-start-2 row-start-1 justify-self-end px-1 py-2 text-[15px] font-medium underline-offset-4 hover:underline sm:col-start-3">
          {signedIn ? "Mis búsquedas" : "Ingresar"}
        </Link>
      </div>
    </header>
  );
}
