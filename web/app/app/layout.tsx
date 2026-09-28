import { BottomNav, MobileInboxLink, TopNav } from "@/components/app/app-nav";
import { InboxProvider } from "@/components/app/inbox-provider";
import { Logo } from "@/components/logo";
import { requireUser } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";

export default async function AppLayout({ children }: LayoutProps<"/app">) {
  const user = await requireUser();
  const supabase = await createClient();
  const { count } = await supabase
    .from("notifications")
    .select("id", { count: "exact", head: true })
    .eq("channel", "web")
    .eq("status", "sent")
    .is("opened_at", null);

  return (
    <InboxProvider userId={user.id} initialUnread={count ?? 0}>
      <div className="flex min-h-dvh flex-col bg-muted/30">
        <header className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur">
          <div className="mx-auto flex h-14 w-full max-w-5xl items-center justify-between gap-4 px-4">
            <Logo href="/app" />
            <TopNav />
            <MobileInboxLink />
          </div>
        </header>
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 pt-5 pb-24 md:pb-10">{children}</main>
        <BottomNav />
      </div>
    </InboxProvider>
  );
}
