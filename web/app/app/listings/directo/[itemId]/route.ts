import { type NextRequest, NextResponse } from "next/server";

import { requestOrigin } from "@/lib/origin";
import { createClient } from "@/lib/supabase/server";

/**
 * Agencias (spec §4.4 paso 4.3): a 'directo' listing's url is
 * /app/listings/directo/<item id>, the only page that car has. It sends to the
 * listing page by its listings id; 404 when the worker hasn't written it.
 */
export async function GET(request: NextRequest, ctx: RouteContext<"/app/listings/directo/[itemId]">) {
  const { itemId } = await ctx.params;
  if (!/^\d+$/.test(itemId)) return new NextResponse(null, { status: 404 });
  const supabase = await createClient();
  const { data } = await supabase.from("listings").select("id").eq("source", "directo").eq("external_id", itemId).maybeSingle();
  if (!data) return new NextResponse(null, { status: 404 });
  const response = NextResponse.redirect(new URL(`/app/listings/${data.id}${request.nextUrl.search}`, requestOrigin(request)), 302);
  response.headers.set("Cache-Control", "no-store");
  return response;
}
