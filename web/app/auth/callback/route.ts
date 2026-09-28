import { type NextRequest, NextResponse } from "next/server";

import { safeNext } from "@/lib/navigation";
import { afterSignIn } from "@/lib/signup";
import { createClient } from "@/lib/supabase/server";
import { requestOrigin } from "@/lib/origin";

/** The magic link lands here with a PKCE code (sección 9, Auth). */
export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const origin = requestOrigin(request);
  const code = searchParams.get("code");
  const next = safeNext(searchParams.get("next"));
  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      await afterSignIn(supabase);
      return NextResponse.redirect(new URL(next, origin));
    }
  }
  return NextResponse.redirect(new URL(`/login?error=link&next=${encodeURIComponent(next)}`, origin));
}
