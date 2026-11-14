import "server-only";

import { requireAdmin } from "@/lib/admin";
import type { SearchNotificationRow, SearchRow } from "@/lib/admin-searches-data";
import { type EventRow, type NotificationRow, type PaymentRow, type UserRow } from "@/lib/admin-users-data";
import { createAdminClient } from "@/lib/supabase/admin";

type Page = PromiseLike<{ data: unknown[] | null; error: { message: string } | null }>;
const PAGE = 1000;

/** Every row of a read, page by page: the REST API returns at most 1000 per request. */
export async function readAll<T>(read: (from: number, to: number) => Page, cap = 50_000): Promise<T[]> {
  const rows: T[] = [];
  while (rows.length < cap) {
    const { data, error } = await read(rows.length, rows.length + PAGE - 1);
    if (error) throw new Error(`admin read failed: ${error.message}`);
    rows.push(...((data ?? []) as T[]));
    if (!data || data.length < PAGE) break;
  }
  return rows;
}

/** What the «Usuarios» dashboard needs, read with the service role. */
export async function loadUsersInput() {
  await requireAdmin();
  const db = createAdminClient();
  const [users, events, notifications, payments] = await Promise.all([
    readAll<UserRow>((a, b) =>
      db.from("admin_users").select("id,email,plan,plan_expires_at,role,created_at,telegram_linked,email_only,searches,enabled_searches,waitlist_plan").order("created_at").range(a, b),
    ),
    readAll<EventRow>((a, b) =>
      db.from("events").select("user_id,name,props,created_at")
        .not("name", "in", "(alert_sent,lifecycle_email_sent,founder_email_sent)")
        .order("id").range(a, b),
    ),
    readAll<NotificationRow>((a, b) =>
      db.from("notifications").select("user_id,sent_at,opened_at,clicked_at").eq("status", "sent").order("id").range(a, b),
    ),
    readAll<PaymentRow>((a, b) => db.from("commercial_payments").select("user_id,amount,paid_at,refunded_at").order("id").range(a, b)),
  ]);
  return { users, events, notifications, payments };
}

/** What the «Búsquedas» dashboard needs: the searches with their radius, and their sent alerts. */
export async function loadSearchesInput() {
  await requireAdmin();
  const db = createAdminClient();
  const [searches, radii, notifications] = await Promise.all([
    readAll<SearchRow>((a, b) => db.from("admin_searches").select("*").order("id").range(a, b)),
    readAll<{ id: number; radius_km: number | null }>((a, b) => db.from("search_profiles").select("id,radius_km").order("id").range(a, b)),
    readAll<SearchNotificationRow>((a, b) =>
      db.from("notifications").select("search_profile_id,opened_at,clicked_at").eq("status", "sent").order("id").range(a, b),
    ),
  ]);
  const radius = new Map(radii.map((r) => [r.id, r.radius_km]));
  return { searches: searches.map((s) => ({ ...s, radius_km: radius.get(s.id) ?? null })), notifications };
}
