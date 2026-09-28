import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";

import { supabaseAnonKey, supabaseUrl } from "@/lib/env";
import { requestOrigin } from "@/lib/origin";

/**
 * Refreshes the Supabase session on every navigation and keeps /app/** for
 * signed-in users. /r/<id> stays public: an alert link must work (and count)
 * before the user signs in.
 */
export async function proxy(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(supabaseUrl, supabaseAnonKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet, headers) {
        cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
        response = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
        Object.entries(headers).forEach(([key, value]) => response.headers.set(key, value));
      },
    },
  });

  const { data } = await supabase.auth.getClaims();
  const signedIn = Boolean(data?.claims?.sub);
  const { pathname, search } = request.nextUrl;

  if (!signedIn && pathname.startsWith("/app")) {
    const url = new URL(`/login?next=${encodeURIComponent(pathname + search)}`, requestOrigin(request));
    return redirectWith(url, response);
  }
  if (signedIn && pathname === "/login") {
    return redirectWith(new URL("/app", requestOrigin(request)), response);
  }
  return response;
}

/** A redirect that keeps the refreshed session cookies. */
function redirectWith(url: URL, from: NextResponse) {
  const redirect = NextResponse.redirect(url);
  from.cookies.getAll().forEach((cookie) => redirect.cookies.set(cookie));
  return redirect;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)"],
};
