import { AcquirePlanButton, MobileNav, TopNav } from "@/components/app/app-nav";
import { Logo } from "@/components/logo";
import { canViewHealth } from "@/lib/health-auth";
import { isAdmin } from "@/lib/admin";
import { requireUser } from "@/lib/auth";
import { canAcquirePlan, type PlanLimits } from "@/lib/pro";
import { createClient } from "@/lib/supabase/server";

export default async function AppLayout({ children }: LayoutProps<"/app">) {
  await requireUser();
  const supabase = await createClient();
  const [admin, healthOwner, { data: rawAccess, error: accessError }] = await Promise.all([
    isAdmin(), canViewHealth(), supabase.rpc("my_plan_snapshot"),
  ]);
  const showAcquirePlan = !accessError && canAcquirePlan(rawAccess as PlanLimits | null);

  return (
    <>
      <div className="flex min-h-dvh flex-col bg-background">
        <header className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur-sm">
          <div className="mx-auto flex h-15 w-full max-w-6xl items-center gap-3 px-4 sm:px-6 md:gap-7 lg:px-10">
            <Logo href="/app" className="shrink-0 whitespace-nowrap" />
            <TopNav admin={admin} healthOwner={healthOwner} canAcquirePlan={showAcquirePlan} />
            {/* Below 360 px «Planes» gives way, so the icons never push the page sideways. */}
            <div className="ml-auto flex h-full items-center gap-1.5 md:hidden">
              <AcquirePlanButton canAcquirePlan={showAcquirePlan} className="h-8 px-2.5 text-[13px] max-[359px]:hidden" />
              <MobileNav healthOwner={healthOwner} />
            </div>
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 pt-7 pb-16 sm:px-6 md:pt-10 lg:px-10">
          {children}
        </main>
      </div>
    </>
  );
}
