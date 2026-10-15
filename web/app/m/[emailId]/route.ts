import { type NextRequest, NextResponse } from "next/server";

import { type AlertLink, alertLinkOwner, continuePage, isAppPath, signedAction, signInFromAlertLink } from "@/lib/alert-session";
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

const GONE = "Este link no existe o ya no está disponible.";

function redirect(request: NextRequest, target: string, status: 302 | 303) {
  const response = NextResponse.redirect(new URL(target, requestOrigin(request)), status);
  response.headers.set("Cache-Control", "no-store");
  return response;
}

/**
 * Without a session /app sends an email-only account (no password) to the
 * login; a signed, recent email link signs the owner in first (lib/alert-session.ts).
 */
async function handle(request: NextRequest, emailId: string, count: boolean) {
  const id = lifecycleEmailId(emailId);
  const target = lifecycleTarget(id == null ? null : count ? await track(id) : await peek(id));
  if (id == null || !target) return new NextResponse(GONE, { status: 404 });
  // Only a real click may sign someone in: never a link preview or a HEAD request.
  const link: AlertLink = { scope: "m", id, signature: request.nextUrl.searchParams.get("s") };
  if (count && isAppPath(target) && await alertLinkOwner(link)) {
    return continuePage(signedAction(`/m/${id}`, { s: link.signature }));
  }
  return redirect(request, target, 302);
}

export async function GET(request: NextRequest, ctx: RouteContext<"/m/[emailId]">) {
  const { emailId } = await ctx.params;
  return handle(request, emailId, !isPreview(request.headers.get("user-agent")));
}

export async function HEAD(request: NextRequest, ctx: RouteContext<"/m/[emailId]">) {
  const { emailId } = await ctx.params;
  return handle(request, emailId, false);
}

/** The page of a signed link posts here (the click was already counted): sign in, then go on. */
export async function POST(request: NextRequest, ctx: RouteContext<"/m/[emailId]">) {
  if (request.headers.get("origin") !== requestOrigin(request)) return new NextResponse("Solicitud inválida", { status: 403 });
  const { emailId } = await ctx.params;
  const id = lifecycleEmailId(emailId);
  const target = lifecycleTarget(id == null ? null : await peek(id));
  if (id == null || !target) return new NextResponse(GONE, { status: 404 });
  const link: AlertLink = { scope: "m", id, signature: request.nextUrl.searchParams.get("s") };
  const owner = await alertLinkOwner(link);
  if (owner !== null) await signInFromAlertLink(owner, link);
  return redirect(request, target, 303);
}
