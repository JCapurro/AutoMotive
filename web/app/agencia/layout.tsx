import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { DealerNav } from "@/components/agencia/dealer-nav";
import { Logo } from "@/components/logo";
import { currentUser } from "@/lib/auth";
import { webConfig } from "@/lib/config";
import { myDealer } from "@/lib/dealer-server";

export const metadata: Metadata = { title: { default: "Mi agencia", template: "%s · Mi agencia · Ese Auto" }, robots: { index: false } };
// Reads the session and live stock: never prerendered.
export const dynamic = "force-dynamic";

/**
 * Agencias (docs/superpowers/specs/2026-11-18-agencias-design.md §6.1): the
 * dealer panel. With dealer_program.enabled off the whole panel is a 404 for
 * everyone, signed in or not (as before the program), so it doesn't announce
 * itself; only then does it ask for a session.
 */
export default async function DealerLayout({ children }: LayoutProps<"/agencia">) {
  const { dealerProgram } = await webConfig();
  if (!dealerProgram.enabled) notFound();
  if (!(await currentUser())) redirect(`/login?next=${encodeURIComponent("/agencia")}`);
  const dealer = await myDealer();

  return (
    <div className="flex min-h-dvh flex-col bg-background">
      <header className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur-sm">
        <div className="mx-auto w-full max-w-6xl space-y-2 px-4 py-2 sm:px-6 lg:px-10">
          <div className="flex h-10 items-center justify-between gap-4">
            <div className="flex min-w-0 items-center gap-2">
              <Logo href="/agencia" className="shrink-0 whitespace-nowrap" />
              <span className="truncate text-sm font-semibold">{dealer ? dealer.name : "Agencias"}</span>
            </div>
            <Link href="/app" className="shrink-0 text-sm font-medium hover:underline">
              Ir a mis búsquedas
            </Link>
          </div>
          {dealer ? <DealerNav newLeads={dealer.counts.leads_new} /> : null}
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl min-w-0 flex-1 px-4 pt-6 pb-16 sm:px-6 lg:px-10">{children}</main>
    </div>
  );
}
