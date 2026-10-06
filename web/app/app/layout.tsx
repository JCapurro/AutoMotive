import { BottomNav, TopNav } from "@/components/app/app-nav";
import { Logo } from "@/components/logo";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { canViewHealth } from "@/lib/health-auth";
import { isAdmin } from "@/lib/admin";
import { requireUser } from "@/lib/auth";

export default async function AppLayout({ children }: LayoutProps<"/app">) {
  await requireUser();
  const [admin, healthOwner] = await Promise.all([isAdmin(), canViewHealth()]);

  return (
    <>
      <div className="flex min-h-dvh flex-col bg-background">
        <header className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur-sm">
          <div className="mx-auto flex h-15 w-full max-w-6xl items-center gap-7 px-4 sm:px-6 lg:px-10">
            <Logo href="/app" />
            <TopNav admin={admin} healthOwner={healthOwner} />
            <Button asChild variant="outline" className="ml-auto h-9 px-3.5 md:hidden">
              <Link href="/app/pro">Adquirir plan</Link>
            </Button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 pt-7 pb-28 sm:px-6 md:pt-10 md:pb-16 lg:px-10">
          {children}
        </main>
        <BottomNav healthOwner={healthOwner} />
      </div>
    </>
  );
}
