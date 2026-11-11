import { NextResponse, type NextRequest } from "next/server";

import { requestOrigin } from "@/lib/origin";

/**
 * Private founder link for agencies: /fundador/<code>. It only forwards to the
 * plans page with the code; the proxy sends anyone without a session through
 * /login first, and the price is checked again when the checkout starts.
 */
export async function GET(request: NextRequest, { params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const target = new URL("/app/pro", requestOrigin(request));
  target.searchParams.set("plan", "pro_monthly");
  if (/^[a-f0-9]{8,32}$/.test(code)) target.searchParams.set("fundador", code);
  return NextResponse.redirect(target, 303);
}
