import { type NextRequest, NextResponse } from "next/server";

import { lifecycleEmailId, lifecycleTarget } from "@/lib/lifecycle-click";
import { requestOrigin } from "@/lib/origin";
import { createAdminClient } from "@/lib/supabase/admin";
import { isPreview } from "@/lib/tracking";

// Clicks must hit the database every time.
export const dynamic = "force-dynamic";

/** Records the click (service role: the link may be opened before signing in); returns the target. */
async function track(id: number): Promise<string | null> {
  const { data, error } = await createAdminClient().rpc("track_lifecycle_click", { p_id: id });
  if (error) throw new Error(`track_lifecycle_click: ${error.message}`);
  return data ?? null;
}

/** Where the button leads, without recording anything (HEAD, link previews). */
async function peek(id: number): Promise<string | null> {
  const { data } = await createAdminClient()
    .from("lifecycle_emails")
    .select("target")
    .eq("id", id)
    .eq("status", "sent")
    .maybeSingle();
  return data?.target ?? null;
}

async function handle(request: NextRequest, emailId: string, count: boolean) {
  const id = lifecycleEmailId(emailId);
  const target = lifecycleTarget(id == null ? null : count ? await track(id) : await peek(id));
  if (!target) return new NextResponse("Este link no existe o ya no está disponible.", { status: 404 });
  const response = NextResponse.redirect(new URL(target, requestOrigin(request)), 302);
  response.headers.set("Cache-Control", "no-store");
  return response;
}

export async function GET(request: NextRequest, ctx: RouteContext<"/m/[emailId]">) {
  const { emailId } = await ctx.params;
  return handle(request, emailId, !isPreview(request.headers.get("user-agent")));
}

export async function HEAD(request: NextRequest, ctx: RouteContext<"/m/[emailId]">) {
  const { emailId } = await ctx.params;
  return handle(request, emailId, false);
}
