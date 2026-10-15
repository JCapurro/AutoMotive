import { type NextRequest, NextResponse } from "next/server";

import { createAdminClient } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";
import { type ClickTarget, destination, isPreview, parseClick } from "@/lib/tracking";
import { requestOrigin } from "@/lib/origin";

// Clicks must hit the database every time.
export const dynamic = "force-dynamic";

type Row = { listing_id: number; url: string };

/** Records the click (service role: the link may be opened before signing in). */
async function track(notificationId: number, to: ClickTarget, listingId: number | null): Promise<Row | null> {
  const { data, error } = await createAdminClient().rpc("track_notification_click", {
    p_notification_id: notificationId,
    p_to: to,
    p_listing_id: listingId ?? undefined,
  });
  if (error) throw new Error(`track_notification_click: ${error.message}`);
  return data?.[0] ?? null;
}

/** Where the link leads, without recording anything (HEAD, link previews). */
async function peek(notificationId: number, listingId: number | null): Promise<Row | null> {
  const admin = createAdminClient();
  const { data: n } = await admin
    .from("notifications")
    .select("listing_id, payload")
    .eq("id", notificationId)
    .maybeSingle();
  if (!n) return null;
  const wanted = listingId ?? n.listing_id;
  const items = ((n.payload as { items?: { listing_id?: number }[] } | null)?.items ?? []).map((i) =>
    Number(i.listing_id),
  );
  if (wanted == null || (listingId != null && listingId !== n.listing_id && !items.includes(listingId))) return null;
  const { data: listing } = await admin.from("listings").select("id, url").eq("id", wanted).maybeSingle();
  return listing ? { listing_id: listing.id, url: listing.url } : null;
}

/**
 * An email-only account (free search) has no password: without a session on
 * this browser the detail page would end at the login. Its alert opens the
 * listing at the source instead; the email already shows the comparison.
 */
async function signedOutEmailOnly(notificationId: number): Promise<boolean> {
  const { data: claims } = await (await createClient()).auth.getClaims();
  if (claims?.claims?.sub) return false;
  const admin = createAdminClient();
  const { data: n } = await admin.from("notifications").select("user_id").eq("id", notificationId).maybeSingle();
  if (!n) return false;
  const { data: profile } = await admin.from("profiles").select("email_only").eq("id", n.user_id).maybeSingle();
  return profile?.email_only === true;
}

async function handle(request: NextRequest, notificationId: string, count: boolean) {
  const click = parseClick(notificationId, request.nextUrl.searchParams);
  if (!click) return new NextResponse("Link inválido", { status: 404 });
  const row = count
    ? await track(click.notificationId, click.to, click.listingId)
    : await peek(click.notificationId, click.listingId);
  if (!row) return new NextResponse("Esta alerta no existe o ya no está disponible.", { status: 404 });
  const to = click.to === "detail" && await signedOutEmailOnly(click.notificationId) ? "listing" : click.to;
  const url = new URL(destination(to, row, click.notificationId), requestOrigin(request));
  const response = NextResponse.redirect(url, 302);
  response.headers.set("Cache-Control", "no-store");
  return response;
}

export async function GET(request: NextRequest, ctx: RouteContext<"/r/[notificationId]">) {
  const { notificationId } = await ctx.params;
  return handle(request, notificationId, !isPreview(request.headers.get("user-agent")));
}

export async function HEAD(request: NextRequest, ctx: RouteContext<"/r/[notificationId]">) {
  const { notificationId } = await ctx.params;
  return handle(request, notificationId, false);
}
