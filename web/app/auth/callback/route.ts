import { type NextRequest, NextResponse } from "next/server";

import { afterRecoveryLink, completeWithGoogle } from "@/lib/account-proof";
import { afterRecovery, RESET_PASSWORD_PATH, safeNext } from "@/lib/navigation";
import { afterSignIn } from "@/lib/signup";
import { createClient } from "@/lib/supabase/server";
import { requestOrigin } from "@/lib/origin";
import { GET as confirmEmail } from "../confirm/route";

/** Exchange an email or OAuth PKCE code for a server session. */
export function HEAD() {
  return new NextResponse(null, { headers: { "Cache-Control": "private, no-store" } });
}

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  if (searchParams.has("token_hash")) return confirmEmail(request);
  const origin = requestOrigin(request);
  const code = searchParams.get("code");
  const next = safeNext(searchParams.get("next"));
  const recovery = new URL(next, origin).pathname === RESET_PASSWORD_PATH;
  if (code && !searchParams.has("error")) {
    const supabase = await createClient();
    const { data, error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      if (recovery) return NextResponse.redirect(new URL(await afterRecoveryLink(supabase, next), origin));
      if (searchParams.get("provider") === "google" && data?.user?.identities?.some((identity) => identity.provider === "google")) {
        await afterSignIn(supabase, "google");
        await completeWithGoogle(supabase, data.user);
      } else await afterSignIn(supabase);
      return NextResponse.redirect(new URL(next, origin));
    }
  }
  if (searchParams.get("provider") === "google") {
    return NextResponse.redirect(new URL(`/login?error=google&next=${encodeURIComponent(next)}`, origin));
  }
  const failed = new URLSearchParams({ error: "link", mode: recovery ? "recover" : "login", next: recovery ? afterRecovery(next) : next });
  return NextResponse.redirect(new URL(`/login?${failed}`, origin));
}
