import type { NextRequest } from "next/server";

import { openTarget } from "@/lib/email-open";
import { createAdminClient } from "@/lib/supabase/admin";

// Opens must hit the database every time.
export const dynamic = "force-dynamic";

/** A transparent 1×1 GIF. */
const PIXEL = Buffer.from("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7", "base64");

/**
 * The 1 px image in every email (worker/notifications/links.py open_pixel):
 * the first load marks it opened (20261109120000_email_opens). The image
 * always answers, whatever the id, so a failure never shows in the email.
 */
export async function GET(request: NextRequest, ctx: RouteContext<"/o/[id]">) {
  const target = openTarget((await ctx.params).id, request.nextUrl.searchParams.get("k"));
  if (target) {
    const { error } = await createAdminClient().rpc("track_email_open", { p_kind: target.kind, p_id: target.id });
    if (error) console.error("track_email_open:", error.message);
  }
  return new Response(PIXEL, {
    headers: { "Content-Type": "image/gif", "Cache-Control": "no-store, max-age=0", "Content-Length": String(PIXEL.length) },
  });
}
