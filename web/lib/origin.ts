import type { NextRequest } from "next/server";

/**
 * The origin the browser used. `request.nextUrl.origin` can differ from it
 * (the dev server reports `localhost` for 127.0.0.1), and a redirect to
 * another host loses the session cookies.
 */
export function requestOrigin(request: NextRequest): string {
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  const proto = request.headers.get("x-forwarded-proto") ?? request.nextUrl.protocol.replace(/:$/, "");
  return host ? `${proto}://${host}` : request.nextUrl.origin;
}
