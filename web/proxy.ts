import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";

import { encodeOrigin, ORIGIN_COOKIE, ORIGIN_MAX_AGE, originFromRequest, skipsOrigin } from "@/lib/acquisition";
import { supabaseAnonKey, supabaseUrl } from "@/lib/env";
import { isHealthOwner } from "@/lib/health-access";
import { trackingAllowed } from "@/lib/meta-pixel";
import { requestOrigin } from "@/lib/origin";

/**
 * Refreshes the Supabase session on every navigation and keeps /app/** for
 * signed-in users and /admin/** for admins (sección 10; the pages check again
 * on the server). /r/<id> stays public: an alert link must work (and count)
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

  const admin = pathname === "/admin" || pathname.startsWith("/admin/");
  if (!signedIn && (pathname.startsWith("/app") || admin)) {
    const url = new URL(`/login?next=${encodeURIComponent(pathname + search)}`, requestOrigin(request));
    return redirectWith(url, response);
  }
  if (pathname === "/app/health" || pathname.startsWith("/app/health/")) {
    const { data: verified, error } = await supabase.auth.getUser();
    if (error || !isHealthOwner(verified.user)) {
      const denied = new NextResponse("Not found", { status: 404, headers: { "Cache-Control": "private, no-store" } });
      response.cookies.getAll().forEach((cookie) => denied.cookies.set(cookie));
      return denied;
    }
  }
  if (admin) {
    const { data: profile } = await supabase.from("profiles").select("role").eq("id", data!.claims!.sub).maybeSingle();
    if (profile?.role !== "admin") return redirectWith(new URL("/app", requestOrigin(request)), response);
  }
  if (signedIn && pathname === "/login") {
    return redirectWith(new URL("/app", requestOrigin(request)), response);
  }
  if (!signedIn) keepFirstTouch(request, response);
  return response;
}

/**
 * The first page an anonymous visitor opens, with its UTM, ad click id and
 * referrer (lib/acquisition.ts), kept until signup copies it into the
 * signup_completed event. Not when tracking was refused, not on prefetches or
 * RSC requests, and never rewritten while it lives.
 */
function keepFirstTouch(request: NextRequest, response: NextResponse) {
  if (request.method !== "GET" || request.cookies.has(ORIGIN_COOKIE)) return;
  if (!trackingAllowed(request.headers.get("cookie") ?? "")) return;
  const h = request.headers;
  if (h.has("rsc") || h.has("next-router-prefetch") || /prefetch/i.test(h.get("purpose") ?? h.get("sec-purpose") ?? "")) return;
  const dest = h.get("sec-fetch-dest");
  if (dest && dest !== "document") return;
  if (skipsOrigin(request.nextUrl.pathname)) return;
  const url = new URL(request.nextUrl.pathname + request.nextUrl.search, requestOrigin(request));
  response.cookies.set(ORIGIN_COOKIE, encodeOrigin(originFromRequest(url, h.get("referer"))), {
    httpOnly: true, sameSite: "lax", secure: url.protocol === "https:", path: "/", maxAge: ORIGIN_MAX_AGE,
  });
}

/** A redirect that keeps the refreshed session cookies. */
function redirectWith(url: URL, from: NextResponse) {
  const redirect = NextResponse.redirect(url);
  from.cookies.getAll().forEach((cookie) => redirect.cookies.set(cookie));
  return redirect;
}

export const config = {
  // Skips what never reads the session: assets, crawler files, the OG image and the
  // Mercado Pago webhook/cron (each proxy run is an invocation plus a Supabase check).
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml|llms.txt|llms-full.txt|indexnow.txt|opengraph-image|api/mercadopago/|.*\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
