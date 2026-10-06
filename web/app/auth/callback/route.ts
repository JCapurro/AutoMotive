import { type NextRequest, NextResponse } from "next/server";

import { safeNext } from "@/lib/navigation";
import { afterSignIn } from "@/lib/signup";
import { createClient } from "@/lib/supabase/server";
import { requestOrigin } from "@/lib/origin";
import { GET as confirmEmail } from "../confirm/route";

/** Exchange a signup or recovery PKCE code for a server session. */
export function HEAD() {
  return new NextResponse(null, { headers: { "Cache-Control": "private, no-store" } });
}

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  if (searchParams.has("token_hash")) return confirmEmail(request);
  const origin = requestOrigin(request);
  const code = searchParams.get("code");
  const next = safeNext(searchParams.get("next"));
  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      if (next !== "/auth/reset-password") await afterSignIn(supabase);
      return NextResponse.redirect(new URL(next, origin));
    }
  }
  return NextResponse.redirect(new URL(`/login?error=link&mode=${next === "/auth/reset-password" ? "recover" : "login"}&next=${encodeURIComponent(next)}`, origin));
}
