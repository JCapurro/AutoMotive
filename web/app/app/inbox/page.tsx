import { BellOff, ChevronRight } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { MarkOpened } from "@/components/app/mark-opened";
import { requireUser } from "@/lib/auth";
import { NOTIFICATION_TITLE } from "@/lib/copy";
import { ago, money, vehicle } from "@/lib/format";
import { createClient } from "@/lib/supabase/server";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Alertas" };

type WebPayload = {
  web?: { title?: string; vehicle?: string | null; lines?: string[]; notes?: string[] };
  listing?: { make?: string; model?: string; trim?: string; year?: number; title?: string; price?: number; currency?: string };
  items?: DigestItem[];
};
type DigestItem = {
  section: "matches" | "price_drops" | "gone";
  listing_id: number;
  listing?: { make?: string; model?: string; trim?: string; year?: number; title?: string; price?: number; currency?: string };
  match?: { score?: number; level?: string };
};

const DIGEST_SECTION = { matches: "Publicaciones nuevas", price_drops: "Bajaron de precio", gone: "Ya no están disponibles" };

/**
 * The web inbox (§21, sección 7.2): the worker's `web` channel rows. New ones
 * arrive through Realtime (components/app/inbox-provider.tsx refreshes this
 * page). Every link goes through /r/<id> so clicks count (sección 7.3).
 */
export default async function InboxPage() {
  await requireUser();
  const supabase = await createClient();
  const { data: rows } = await supabase
    .from("notifications")
    .select("id, kind, payload, created_at, opened_at, clicked_at, listing_id")
    .eq("channel", "web")
    .eq("status", "sent")
    .order("created_at", { ascending: false })
    .limit(50);
  const notifications = rows ?? [];
  const unopened = notifications.filter((n) => !n.opened_at).map((n) => n.id);
  const now = new Date();

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold tracking-tight">Alertas</h1>
      <MarkOpened ids={unopened} />
      {notifications.length ? (
        <ul className="space-y-2" data-testid="inbox">
          {notifications.map((n) => {
            const p = (n.payload ?? {}) as WebPayload;
            const title = p.web?.title ?? NOTIFICATION_TITLE[n.kind] ?? "Alerta";
            const unread = !n.opened_at;
            if (n.kind === "digest") {
              const items = p.items ?? [];
              return (
                <li key={n.id} className="rounded-xl bg-card p-4 ring-1 ring-foreground/10" data-testid="inbox-item">
                  <div className="flex items-baseline justify-between gap-2">
                    <p className="font-medium">{title}</p>
                    <time className="shrink-0 text-xs text-muted-foreground">hace {ago(n.created_at, now)}</time>
                  </div>
                  {(Object.keys(DIGEST_SECTION) as DigestItem["section"][]).map((section) => {
                    const list = items.filter((i) => i.section === section);
                    if (!list.length) return null;
                    return (
                      <div key={section} className="mt-3 space-y-1">
                        <p className="text-xs font-medium text-muted-foreground">{DIGEST_SECTION[section]}</p>
                        <ul className="space-y-1 text-sm">
                          {list.map((item) => (
                            <li key={item.listing_id}>
                              <a href={`/r/${n.id}?to=detail&l=${item.listing_id}`} className="hover:underline">
                                {vehicle(item.listing ?? {})}
                              </a>
                              {item.listing?.price != null ? (
                                <span className="text-muted-foreground"> · {money(item.listing.price, item.listing.currency)}</span>
                              ) : null}
                            </li>
                          ))}
                        </ul>
                      </div>
                    );
                  })}
                </li>
              );
            }
            return (
              <li key={n.id} data-testid="inbox-item">
                <a
                  href={`/r/${n.id}?to=detail`}
                  className={cn(
                    "flex items-start gap-3 rounded-xl bg-card p-4 ring-1 ring-foreground/10 transition-colors hover:bg-muted/50",
                    unread && "ring-orange-300",
                  )}
                >
                  <span
                    aria-label={unread ? "Sin leer" : undefined}
                    className={cn("mt-2 size-2 shrink-0 rounded-full", unread ? "bg-orange-600" : "bg-transparent")}
                  />
                  <div className="min-w-0 flex-1 space-y-0.5">
                    <div className="flex items-baseline justify-between gap-2">
                      <p className="text-sm font-medium">{title}</p>
                      <time className="shrink-0 text-xs text-muted-foreground">hace {ago(n.created_at, now)}</time>
                    </div>
                    <p className="font-semibold">{p.web?.vehicle ?? vehicle(p.listing ?? {})}</p>
                    {p.web?.lines?.length ? (
                      <p className="text-sm text-muted-foreground">{p.web.lines.join(" · ")}</p>
                    ) : null}
                    {p.web?.notes?.length ? (
                      <p className="truncate text-xs text-muted-foreground">{p.web.notes.join(" · ")}</p>
                    ) : null}
                  </div>
                  <ChevronRight className="mt-1 size-4 shrink-0 text-muted-foreground" aria-hidden />
                </a>
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="space-y-2 py-12 text-center">
          <BellOff className="mx-auto size-8 text-muted-foreground" aria-hidden />
          <p className="font-medium">Todavía no hay alertas</p>
          <p className="text-sm text-muted-foreground">
            Cuando aparezca una publicación nueva que coincida con tus búsquedas, la vas a ver acá al instante.
          </p>
          <Link href="/app" className="text-sm underline">
            Ver mis búsquedas
          </Link>
        </div>
      )}
    </div>
  );
}
