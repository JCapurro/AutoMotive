import type { EmailOtpType } from "@supabase/supabase-js";
import { type NextRequest, NextResponse } from "next/server";

import { afterRecoveryLink } from "@/lib/account-proof";
import { afterRecovery, recoveryNext, safeNext } from "@/lib/navigation";
import { afterSignIn } from "@/lib/signup";
import { createClient } from "@/lib/supabase/server";
import { requestOrigin } from "@/lib/origin";

const tokenTypes = ["signup", "email", "recovery", "email_change", "invite", "magiclink"];

/** Email previews must never consume a one-use token, including HEAD requests. */
export function HEAD() {
  return new NextResponse(null, { headers: { "Cache-Control": "private, no-store" } });
}

/** A used or expired link goes back to the form that sends a new one, keeping where it was headed. */
function failed(origin: string, recovery: boolean, next: string, status?: number) {
  const params = new URLSearchParams({ error: "link", mode: recovery ? "recover" : "login", next: recovery ? afterRecovery(next) : next });
  return NextResponse.redirect(new URL(`/login?${params}`, origin), status);
}

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const origin = requestOrigin(request);
  const tokenHash = searchParams.get("token_hash");
  const type = searchParams.get("type");
  const recovery = type === "recovery";
  // A recovery link may only lead to the password form (carrying its own `next`).
  const next = recovery ? recoveryNext(searchParams.get("next")) : safeNext(searchParams.get("next"));
  if (tokenHash && type && tokenTypes.includes(type)) {
    const url = new URL("/auth/confirm-email", origin);
    url.search = new URLSearchParams({ token_hash: tokenHash, type, next }).toString();
    const response = NextResponse.redirect(url);
    response.headers.set("Cache-Control", "private, no-store");
    response.headers.set("Referrer-Policy", "strict-origin");
    return response;
  }
  return failed(origin, recovery, next);
}

/** Only an explicit same-origin form submission verifies the email. */
export async function POST(request: NextRequest) {
  const origin = requestOrigin(request);
  if (request.headers.get("origin") !== origin) {
    return new NextResponse("Solicitud inválida", { status: 403 });
  }
  const form = await request.formData();
  const tokenHash = String(form.get("token_hash") ?? "");
  const type = String(form.get("type") ?? "") as EmailOtpType;
  const recovery = type === "recovery";
  const next = recovery ? recoveryNext(String(form.get("next") ?? "")) : safeNext(String(form.get("next") ?? ""));
  if (tokenHash && tokenTypes.includes(type)) {
    const supabase = await createClient();
    const { error } = await supabase.auth.verifyOtp({ type, token_hash: tokenHash });
    if (!error) {
      if (recovery) return NextResponse.redirect(new URL(await afterRecoveryLink(supabase, next), origin), 303);
      await afterSignIn(supabase);
      return NextResponse.redirect(new URL(next, origin), 303);
    }
  }
  return failed(origin, recovery, next, 303);
}
