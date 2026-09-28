import { type NextRequest, NextResponse } from "next/server";

import { currentUser } from "@/lib/auth";
import { track } from "@/lib/events";
import { createClient } from "@/lib/supabase/server";

/**
 * "Ver publicación" from the web: records listing_outbound_clicked (§37,
 * Listing Click Rate) and sends the user to the source. From an alert the
 * button goes through /r/<notification_id>?to=listing instead.
 */
export async function GET(request: NextRequest, ctx: RouteContext<"/app/listings/[id]/out">) {
  const { id } = await ctx.params;
  if (!/^\d+$/.test(id)) return new NextResponse(null, { status: 404 });
  const supabase = await createClient();
  const { data: listing } = await supabase.from("listings").select("id, url, source").eq("id", Number(id)).maybeSingle();
  if (!listing) return new NextResponse(null, { status: 404 });
  const user = await currentUser();
  if (user) await track(supabase, user.id, "listing_outbound_clicked", { listing_id: listing.id, source: listing.source });
  const response = NextResponse.redirect(listing.url, 302);
  response.headers.set("Cache-Control", "no-store");
  return response;
}
