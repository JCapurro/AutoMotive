import type { EmailOtpType } from "@supabase/supabase-js";
import { type NextRequest, NextResponse } from "next/server";

import { safeNext } from "@/lib/navigation";
import { afterSignIn } from "@/lib/signup";
import { createClient } from "@/lib/supabase/server";
import { requestOrigin } from "@/lib/origin";

/**
 * For email templates that link with the token hash
 * ({{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=email&next=/app):
 * unlike the PKCE link it also works when opened in another browser.
 */
export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const origin = requestOrigin(request);
  const tokenHash = searchParams.get("token_hash");
  const type = searchParams.get("type") as EmailOtpType | null;
  const recovery = type === "recovery";
  const next = recovery ? "/auth/reset-password" : safeNext(searchParams.get("next"));
  if (tokenHash && type && ["signup", "email", "recovery", "email_change", "invite", "magiclink"].includes(type)) {
    const supabase = await createClient();
    const { error } = await supabase.auth.verifyOtp({ type, token_hash: tokenHash });
    if (!error) {
      if (!recovery) await afterSignIn(supabase);
      return NextResponse.redirect(new URL(next, origin));
    }
  }
  return NextResponse.redirect(new URL(`/login?error=link&mode=${recovery ? "recover" : "signup"}&next=${encodeURIComponent(next)}`, origin));
}
