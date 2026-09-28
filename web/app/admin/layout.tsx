import type { Metadata } from "next";
import Link from "next/link";

import { AdminNav } from "@/components/admin/admin-nav";
import { Logo } from "@/components/logo";
import { requireAdmin } from "@/lib/admin";

export const metadata: Metadata = { title: { default: "Admin", template: "%s · Admin · Automotive" }, robots: { index: false } };

// Backoffice (sección 10): role = 'admin' checked by the proxy and here; the
// pages read with the service role, server-side only.
export default async function AdminLayout({ children }: LayoutProps<"/admin">) {
  const user = await requireAdmin();
  return (
    <div className="flex min-h-dvh flex-col bg-muted/30">
      <header className="sticky top-0 z-30 min-w-0 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto w-full max-w-7xl space-y-2 px-4 py-2">
          <div className="flex h-10 items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <Logo href="/admin" />
              <span className="rounded-md bg-foreground px-1.5 py-0.5 text-[11px] font-semibold tracking-wide text-background uppercase">
                Admin
              </span>
            </div>
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              <span className="hidden truncate sm:inline">{user.email}</span>
              <Link href="/app" className="font-medium text-foreground hover:underline">
                Ir a la app
              </Link>
            </div>
          </div>
          <AdminNav />
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl min-w-0 flex-1 space-y-8 px-4 py-6">{children}</main>
    </div>
  );
}
