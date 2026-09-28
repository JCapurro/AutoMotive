"use client";

import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { NOTIFICATION_TITLE } from "@/lib/copy";
import { createClient } from "@/lib/supabase/client";

type Inbox = { unread: number; refresh: () => Promise<void> };

const InboxContext = createContext<Inbox>({ unread: 0, refresh: async () => {} });

export function useInbox() {
  return useContext(InboxContext);
}

type Row = {
  id: number;
  channel: string;
  status: string;
  kind: string;
  created_at: string;
  opened_at: string | null;
  payload: { web?: { title?: string; vehicle?: string | null } } | null;
};

/**
 * The web inbox (§21): unread web notifications for the badge, kept live with
 * Supabase Realtime on `notifications` (RLS: only the user's own rows arrive).
 * The worker inserts a row as 'queued' and marks it 'sent' right away; the
 * badge counts sent rows nobody opened yet.
 */
export function InboxProvider({
  userId,
  initialUnread,
  children,
}: {
  userId: string;
  initialUnread: number;
  children: React.ReactNode;
}) {
  const [unread, setUnread] = useState(initialUnread);
  const [supabase] = useState(createClient);
  const router = useRouter();
  const pathname = usePathname();
  const onInbox = useRef(pathname === "/app/inbox");
  const announced = useRef(new Set<number>());
  const mountedAt = useRef(0);

  useEffect(() => {
    onInbox.current = pathname === "/app/inbox";
  }, [pathname]);

  const refresh = useCallback(async () => {
    const { count } = await supabase
      .from("notifications")
      .select("id", { count: "exact", head: true })
      .eq("channel", "web")
      .eq("status", "sent")
      .is("opened_at", null);
    setUnread(count ?? 0);
  }, [supabase]);

  useEffect(() => {
    mountedAt.current = Date.now();
    let cancelled = false;
    let channel: ReturnType<typeof supabase.channel> | null = null;

    (async () => {
      // Realtime has to carry the user's token, or RLS filters every row out.
      const { data } = await supabase.auth.getSession();
      if (cancelled) return;
      if (data.session) await supabase.realtime.setAuth(data.session.access_token);
      channel = supabase
        .channel(`inbox:${userId}`)
        .on(
          "postgres_changes",
          { event: "*", schema: "public", table: "notifications", filter: `user_id=eq.${userId}` },
          (change) => {
            const row = change.new as Row | undefined;
            void refresh();
            if (onInbox.current) router.refresh();
            if (
              row?.channel === "web" &&
              row.status === "sent" &&
              !row.opened_at && // opening it (the inbox, another tab) is an update too
              !announced.current.has(row.id) &&
              new Date(row.created_at).getTime() > mountedAt.current - 60_000
            ) {
              announced.current.add(row.id);
              const title = row.payload?.web?.title ?? NOTIFICATION_TITLE[row.kind] ?? "Nueva alerta";
              toast(title, {
                description: row.payload?.web?.vehicle ?? undefined,
                action: { label: "Ver", onClick: () => router.push("/app/inbox") },
              });
            }
          },
        )
        .subscribe();
    })();

    return () => {
      cancelled = true;
      if (channel) void supabase.removeChannel(channel);
    };
  }, [supabase, userId, refresh, router]);

  return <InboxContext.Provider value={{ unread, refresh }}>{children}</InboxContext.Provider>;
}

export function UnreadBadge({ className = "" }: { className?: string }) {
  const { unread } = useInbox();
  if (!unread) return null;
  return (
    <span
      data-testid="inbox-badge"
      aria-label={`${unread} alertas sin leer`}
      className={`inline-flex min-w-5 items-center justify-center rounded-full bg-orange-600 px-1.5 text-[11px] leading-5 font-semibold text-white tabular-nums ${className}`}
    >
      {unread > 99 ? "99+" : unread}
    </span>
  );
}
